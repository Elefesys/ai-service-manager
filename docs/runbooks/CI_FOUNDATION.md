# Foundation CI split — LOCAL/TEST experiment

C0 task: [C6-CI-FOUNDATION-SPLIT](https://github.com/Elefesys/ai-service-manager/pull/28#issuecomment-6137942355).
Base: `4b63d9ad59fee3631b4314211aaae40884488c98`.

## Commands and required gates

- `sh scripts/ci.sh` remains the complete sequential LOCAL verification: pinned build, whole egress script, unchanged backend gate, storage versions, HTTP/frontend smoke and cleanup.
- `sh scripts/ci.sh --foundation-core` runs the same sequence except the egress block, which has its own mandatory CI job. Unknown or extra arguments fail before init/build/Docker.
- `sh scripts/test_telegram_egress.sh` remains unchanged and runs all six lifecycle scenarios together, including E01–E05 and their shared database/receipt assertions.
- Local routing/status regressions: `python -m unittest discover -s tests -p test_ci_foundation.py -v`. These use command doubles; they are not real PostgreSQL/S3/Docker evidence.

| Job | Mandatory work | Timeout |
|---|---|---:|
| foundation-core | Architecture check, pinned build, complete check_backend.sh, storage versions, HTTP/frontend smoke |40min|
| foundation-egress | Fresh init/pinned API image, whole unchanged normal egress script, owned cleanup |25min|
| foundation | Always evaluate both results and their tested SHA, then clean-source check |5min|

`foundation` retains the old required check name. Both child jobs must finish with `success`; failure/cancelled/skipped/empty/unknown results are refused. Their recorded source SHA must equal the aggregate checkout and GitHub SHA. Upload/cleanup/clean failures remain job failures. The jobs use independent disposable runners and never share DB/S3/volumes.

Browser, exact Docker29 compatibility and six connect5-migration jobs retain their previous commands, pins, permissions and timeouts. Total: **11 jobs, ten verification jobs plus the aggregate**. Every checkout keeps its clean-source gate. The aggregate runs after either dependency fails or skips and performs its own clean check even after gate refusal.

## Source-bound evidence and timing

Core keeps `m0-verification-${run_id}` with architecture/ci logs, tested-commit, worktree-status and source archive. Normal egress uses `foundation-egress-normal-${run_id}` with egress log, telegram-egress.json, candidate-egress-source.json, Docker/Compose versions and the same source records. No artifact or report names are shared across runners.

Core emits `FOUNDATION_PHASE mode=... phase=... event=START/END` for setup/build, backend, storage versions, smoke and cleanup. Egress emits separate SETUP/LIFECYCLE/CLEANUP START/END markers. GitHub timestamps measure these phases; runner queue is reported separately from job execution. Aggregate logs include run/attempt, actual source, both child sources/results and source-pairing completion.

Compare full mandatory-job elapsed time and total runner-minutes against both same-tree baselines: main CI38338767227 (foundation28:26) and PR CI38269539356 (foundation35:35). Report setup/build and backend/lifecycle durations separately where available. Twenty minutes is a measurement target, not a timeout or PASS threshold; actual candidate results belong in the single Draft PR receipt.

## Bounded experiment and return

One implementation variant, at most two hours of active changes and two complete PR CI runs. A second run is only for a concrete small wiring fix. No green-SHA reruns for timing, skipped tests, PG parallelism, caches/distribution framework or changes to lifecycle/DB fixtures.

Until C0 acceptance and user merge, main retains the previous sequential CI. If the split has no useful gain, stalls, or needs another path/semantic change, preserve the Draft PR/diff/evidence and return BLOCKED with a DEFERRED recommendation to C0. Do not delete the branch or revert main. Prepare600/cleanup90/state25 and IMPL-05 OPEN/fix DEFERRED remain unchanged.
