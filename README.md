# Director context picker

A Python 3.11 standard-library command-line program that chooses which memory cards go into the prompt for one Director turn. It reads one JSON request on stdin and writes one JSON response line on stdout, following the supplied context request contract.

The selection is a legal set of cards (visible from the head version, not superseded, requirements closed, one card per conflict group, no contradiction pair, within the token budget, all mandatory cards included) that maximizes the summed weight of the features the selected cards cover.

Every number measured in the recorded benchmark run sits in one delimited block under "Results on the public corpus". Nothing in this file stated as measured was estimated.

## Package layout

All paths are relative to the archive root. Every command below is run from that root.

| Path | Purpose |
|---|---|
| `context_solver.py` | Entry point: stdin request, stdout response, exit code 0 (1 only when stdout cannot be written) |
| `dcp_validate.py` | Strict input validation |
| `dcp_model.py` | Active set, requirement closures, conflict masks, legality test |
| `dcp_exact.py` | Exact branch and bound |
| `dcp_profile.py` | Exact knapsack and upper-bound certificate for the certificate profile |
| `dcp_search.py` | Greedy construction and simulated annealing for large requests |
| `dcp_pipeline.py` | Dispatch, deadlines, hard time guard, fallback, response assembly |
| `tests/` | Regression tests, an independent checker, a brute-force oracle, request generators |
| `tools/` | Recorded-run script, results checker, packaging scripts, search tuning script |
| `benchmark_runner.py` | The supplied recorder, unchanged |
| `benchmark_inputs.json` | The supplied public corpus (28 requests), unchanged |
| `director_session.json` | The supplied sample session, unchanged |
| `benchmark_results.json`, `benchmark_run.log` | Output of the recorded run, exactly as the recorder wrote it |
| `.claude-hve-tracking/` | Research, plan, interface, change and review records from development. See "How this was built" |

`.claude-hve-tracking/` documents how the work was done. It is not part of the runtime: nothing in `context_solver.py`, `dcp_*.py`, `tests/` or `tools/` reads it.

## Clean-extraction commands

Requirements: Python 3.11 available as `python3.11`. Docker is needed only to repeat the recorded run. No package installation, no network.

Extract and enter the package:

```sh
unzip director-context.zip -d director-context
cd director-context
```

Solve one request (the supplied sample session):

```sh
python3.11 context_solver.py < director_session.json
```

Expected stdout, one line (the sample has 7 active cards, so the exact method runs and the answer is the same on every run):

```json
{"status":"ok","selected":["closeup","moon","portrait","sleeve_detail"],"tokens":77,"covered":["continuity","costume","face","gesture","identity","lighting","palette"],"utility":61}
```

One diagnostic line goes to stderr, for example `context_solver: method=exact active=7 proven=True elapsed_ms=31`. The elapsed time varies.

Run the local regression suite. It passes from the extracted archive, needs no Docker and no network, and runs about 340 tests in about 100 seconds on the development machine:

```sh
python3.11 -m unittest discover -s tests
```

Check the shipped recorded results against the corpus with the independent checker, and print the per-instance table and the summary figures:

```sh
python3.11 tools/check_results.py .
```

`check_results.py` checks the observation schema, the recorder and corpus hashes, both source inventories (`python_sources_before`, `python_sources_after`) and the entry-point hash. It re-parses each record's raw `stdout` the way the recorder does and judges that object with the independent checker. The optional certificate and consistency capabilities are reported in their own sections and never change the core `RESULT` line or the exit code.

Repeat the recorded run in Docker. The script refuses a directory that already holds `benchmark_results.json`, so copy the package without the two recorder output files first:

```sh
mkdir ../rerun
cp -R context_solver.py dcp_*.py tests tools benchmark_runner.py benchmark_inputs.json director_session.json ../rerun/
bash tools/run_recorded.sh ../rerun
python3.11 tools/check_results.py ../rerun
```

`tools/run_recorded.sh` runs this, with the directory mounted at `/work`:

```sh
docker run --rm --cpus=2 --network none -v "<dir>":/work -w /work python:3.11-slim sh -c 'python benchmark_runner.py --solution context_solver.py --inputs benchmark_inputs.json --output benchmark_results.json > benchmark_run.log 2>&1; rc=$?; echo "rc=$rc"; exit "$rc"'
```

Without Docker, the same recorder runs directly on the host. This exercises the recorder and the checker but is not a 2-vCPU measurement, so `check_results.py` reports the CPU quota assertion as failed; `--allow-wrong` prints everything and exits 0:

```sh
(cd ../rerun && python3.11 benchmark_runner.py --solution context_solver.py --inputs benchmark_inputs.json --output benchmark_results.json > benchmark_run.log 2>&1)
python3.11 tools/check_results.py ../rerun --allow-wrong
```

`tools/build_package.py` and `tools/make_zip.py` produced this archive from the development repository. `build_package.py` copies the three supplied files from a `resources/` directory under `--source` (default: the parent of `tools/`). The extracted archive has no `resources/` directory, so the script stops there with a `missing supplied file` error and cannot be run from the extracted archive.

The final build ran `build_package.py --verify-results`. That mode requires the results file, the run log and the README, and refuses the build unless every packaged `*.py` matches the recorder's `python_sources_after`. The package includes the durable files of `.claude-hve-tracking/`, without any Python file from that folder.

## Method

### Process boundary (`context_solver.py`)

The entry point records `time.perf_counter()` before any other import; every deadline below is measured from that moment. It reads at most 16 MiB plus one byte from stdin and then stops: bytes past the limit are never read or drained, so an oversized request is answered `invalid` even when the producer keeps the pipe open. It writes exactly one JSON line to stdout and one diagnostic line to stderr (`method`, `active`, `proven`, `elapsed_ms`). If anything fails before a response exists, it prints `{"status":"invalid","reason":"internal error"}`.

The exit code is 0 whenever the response line was written. It is 1 only when the write or flush of that line to stdout fails, because an undelivered response is a failure.

### Validation (`dcp_validate.py`)

The request is rejected as `invalid`, with a short ASCII reason, when it breaks any input rule of the contract. Nothing is repaired, defaulted or dropped. Checks include: size at most 16 MiB (`MAX_BYTES`), strict UTF-8, no byte order mark, exactly one JSON object with nothing after it, no duplicate object keys, no fractional, exponent or non-finite numbers, booleans not accepted as integers, no lone surrogate in a card's `text`, exactly the seven top-level keys, exact key sets for versions and cards (`text` optional), identifier syntax, every count and range limit in the contract table, unique IDs, existing references, an acyclic version graph, supersession only over a strict ancestor version, and distinct unordered contradiction pairs with no self-pair. Validation runs before any feasibility test, so `invalid` takes precedence over `infeasible`.

Structurally impossible input is rejected before it is decoded or parsed: the raw bytes are counted, and a request with more commas, brackets and braces, quotes or colons than any valid request can contain is `invalid`. This bounds the memory the parser can be made to use.

`-0` is integer notation and is accepted as integer zero wherever zero is in range.

### Model (`dcp_model.py`)

`build_problem` computes the versions visible from `head`, the active cards (visible and not superseded by a visible card, directly or through a chain), and for each active card its transitive `requires` closure, the cards it conflicts with (same conflict group or a contradiction pair), and the features it covers. Cards are bits of Python integers. A card whose closure leaves the active set, contains a conflict, or cannot be added to the mandatory closure is not usable. The request is `infeasible` only when the mandatory closure itself is not a legal set: a mandatory card that is not active, a requirement on a card that is not active, a group clash or contradiction pair inside the closure, or a closure above the budget. `is_legal` is the single legality test every solver result passes through.

### Dispatch (`dcp_pipeline.py`)

| Condition, tested in this order | Method | Deadline after process start | Constant |
|---|---|---|---|
| Request is in the certificate profile | Exact 0/1 knapsack, then a certificate | 2.5 s | `LARGE_DEADLINE_S` |
| At most 24 active cards | Exact branch and bound | 3.5 s | `EXACT_MAX_ACTIVE`, `EXACT_DEADLINE_S` |
| 25 to 64 active cards | Greedy construction and simulated annealing until 1.0 s, then exact branch and bound seeded with that result until 2.5 s | 1.0 s, 2.5 s | `MID_EXACT_MAX_ACTIVE`, `MID_SEARCH_DEADLINE_S`, `LARGE_DEADLINE_S` |
| More than 64 active cards | Greedy construction and simulated annealing | 2.5 s | `LARGE_DEADLINE_S` |

The active-card count is the contract's count: after visibility and supersession, before unusable cards are removed. If the profile solver cannot finish in time, the request falls through to the size-based rows.

The deadlines in the table are cooperative: each solver reads the clock itself. A hard guard backs them. It depends on `signal.setitimer`, which Linux and macOS have: there a real-time alarm fires 4.0 s after process start (`HARD_DEADLINE_S`) and interrupts a stage that ignored its deadline. The answer is then the best legal set already held, else the mandatory closure, and the stderr line shows `method=watchdog`.

### Exact search (`dcp_exact.py`)

Depth-first branch and bound over the usable cards. Each node either takes a card together with its whole requirement closure or excludes the card and everything that depends on it. Two upper bounds prune: a fractional knapsack over the remaining cards' own gains and tokens, and the weight of the features the remaining cards can still reach. Both bounds ignore constraints, so they never cut off a better legal set. The search starts from a greedy solution. When the search space is exhausted before the deadline, the result is a maximum-utility legal set and the stderr line shows `proven=True`. When the deadline arrives first, the best legal set found so far is returned and the line shows `proven=False`.

### Certificate profile (`dcp_profile.py`)

The profile is the one the contract defines: every card of the request has an empty `requires` and a null `conflict_group`, `contradictions` is empty, and no feature is covered by more than one active card. Card values are then additive, and the problem is a 0/1 knapsack with the mandatory cards forced. `solve_profile` solves it exactly by dynamic programming over the token budget.

`build_certificate` sets each feature price to `weight * scale` and tries a small set of budget prices: zero, and the value per token of the card at which a fractional greedy fill crosses the budget and of its two neighbors. It keeps the price with the smallest bound `U` and returns the certificate only when `100 * U <= 105 * utility * scale` holds for the set actually returned. Otherwise the response carries no certificate. A response outside the profile never carries one.

### Large-request search (`dcp_search.py`)

`solve_large` builds three greedy solutions on top of the mandatory closure, each adding one card with its closure at a time: best gain per added token, best gain per card that the addition would block, and best plain gain. It keeps the best of the three.

Simulated annealing over legal sets then runs until the deadline. One move picks a random usable card that is not selected. If it conflicts with selected cards, a second random card is drawn and the one with fewer conflicts is used. The move removes the selected cards that conflict with the card together with their dependents, adds the card's closure, and, while the set is over budget, sheds the unit with the least lost weight per freed token among `DROP_SAMPLE` (8) sampled cards. A move that would remove a mandatory card is skipped. Every set the search holds is legal.

A move is scored by utility minus a small token price (`LAMBDA`), so that at equal utility the leaner set wins. A move that lowers the score is accepted with a probability that falls as the temperature falls, and is undone otherwise. The temperature cools from `T_HOT` to `T_COLD` over a round of `ROUND_MOVES` (5,000) moves. Each round restarts from the best set seen, refilled greedily.

The function returns the best legal set seen (highest utility, then fewest tokens), checked with `is_legal`; failing that the greedy result, and failing that the mandatory closure. The random generator is `random.Random` seeded with a fixed value (`DEFAULT_SEED`). The search is bounded by the wall clock, not by a move count, so the number of moves varies with machine speed and load and the result is not deterministic between runs.

Evidence, with its limits:

- On the 13 large coupled public requests, each was solved five times at a 2.0 s search deadline: three seeds, and two renamed and shuffled copies. Eleven requests gave one identical value on all five runs. The other two spread by 6 in 54,795 and by 23 in 71,378.
- An earlier version of the search was bimodal on these requests, for example 61,253 or 73,602 on the same request. That is why it was replaced.
- Nothing is proven optimal above 64 active cards.
- No comparison utilities are public, so the 99 percent bar is not measured.
- On a much slower host fewer moves fit in the time budget and the weaker mode could reappear. It was seen once in 8 seeds when the search was limited to 60,000 moves on one request.

### Fallback (`dcp_pipeline.py`)

Once validation and model construction have succeeded, the pipeline answers `ok` with a legal set that is at least the mandatory closure, whatever a solver raises. An exception in a solver is written to stderr and the best legal set found so far is kept. The hard time guard takes the same path. A result is accepted only if `is_legal` passes and its utility is not below the current best. The floor is the mandatory closure, which is legal by construction. The final set is checked with `is_legal` once more before the response is built.

Two paths answer `invalid` for a request that may be valid: an unexpected exception inside validation (`internal error`), and an unexpected exception while building the model (`internal error: model construction failed`). The hard time guard firing before the model exists ends in the same answer. Both would be wrong answers for a valid request. They exist so that the process still returns one well-formed line. Tests force both paths.

A last resort sits behind them: if building the `ok` response fails for the chosen set, for the mandatory closure, and for a helper-free form of the mandatory closure, the answer is `invalid` with `internal error`.

## Tests

The regression command runs everything in `tests/` and passes from the extracted archive.

| File | What it shows |
|---|---|
| `checker.py` | Independent legality and response checker written from the contract. It imports nothing from the solver |
| `oracle.py` | Brute-force maximum utility by subset enumeration, independent of the solver |
| `gen.py` | Seeded generators: random valid requests, contract-maximum requests, renamed and shuffled equivalent copies |
| `test_checker_oracle.py` | The checker, oracle and generators against hand-derived values |
| `test_validate.py` | One accepting and one rejecting case for every input rule |
| `test_model.py` | Visibility, supersession, closures, conflicts, feasibility, legality |
| `test_exact.py` | Exact search against the oracle, 24-card stress families, 24-card requests with a brute-forced reduced core, deadline behavior |
| `test_profile.py` | Profile detection, exact knapsack against the oracle, certificate validity and the 5% test |
| `test_search.py` | Large search: legality, quality against the oracle on small requests, return within 50 ms of the deadline, never below the greedy result |
| `test_differential.py` | 320 generated requests (1 to 14 active cards) through the pipeline against the checker and oracle, 19 to 22 active cards against the oracle, 23 and 24 active cards against a brute-forced reduced core, and single-rule mutations that must be `invalid` |
| `test_cli.py` | The process contract (one line, exit 0, exit 1 when stdout cannot be written, any working directory, oversize and garbage input), every fallback path, and contract-maximum requests |
| `test_corpus.py` | The 28 public requests through the CLI: checker verdict for each, oracle equality up to 18 active cards, certificates on profile requests and none elsewhere, host wall time, consistency reported |
| `test_reference_scenarios.py` | 102 hand-written scenarios (38 `ok`, 8 `infeasible`, 56 `invalid`) through the CLI |
| `test_tools.py` | The packaging and results tools, without Docker |

## Results on the public corpus

Source: `benchmark_results.json` and `benchmark_run.log`, written by the unchanged recorder in the environment described below, and summarized by `python3.11 tools/check_results.py .`. Every request is listed, including the invalid and infeasible ones.

The corpus has 28 requests: 24 answer `ok`, 2 answer `invalid` (`i_93a288225d57a93686`, `i_57be790be38419e246`) and 2 answer `infeasible` (`i_6bf2ce5fc66d4bad9e`, `i_354f04e366ba47a0e5`). There are no timeouts and no malformed responses, and the independent checker accepts every response.

The three small instances equal the brute-force optimum. The three mid instances (36, 48 and 64 active cards) equal optima proven by long exact runs outside the time limit: 5,471, 6,659 and 8,606.

Every measured number of the recorded run is in the block below.

<!-- BEGIN MEASURED -->

Status counts: `ok` 24, `invalid` 2, `infeasible` 2. Timed out: 0. Records failing the checker: 0 of 28.

| id | active cards | status | utility | tokens | wall ms | peak RSS MiB | checker verdict |
|---|---|---|---|---|---|---|---|
| `i_353b0868e8bfb0bb1c` | 3 | ok | 60 | 20 | 110 | 16.6 | pass |
| `i_d377627acc7b53786a` | 476 | ok | 73602 | 1953 | 2520 | 16.3 | pass |
| `i_613d784770e53c543d` | 428 | ok | 120 | 1735 | 2590 | 16.3 | pass |
| `i_6f0cb82b21cc17afba` | 380 | ok | 223 | 1603 | 2510 | 16.3 | pass |
| `i_93a288225d57a93686` | - | invalid | - | - | 40 | 16.0 | pass |
| `i_5fccaf00f31313dcfc` | 428 | ok | 111 | 1458 | 2700 | 16.3 | pass |
| `i_3fa5a35f7c751fc671` | 64 | ok | 8606 | 296 | 2630 | 15.9 | pass |
| `i_658192e99b3806aff2` | 12 | ok | 1399 | 54 | 70 | 15.9 | pass |
| `i_5568451c1df999c2c4` | 3 | ok | 70 | 20 | 30 | 15.9 | pass |
| `i_d755f5d407b0d86c60` | 476 | ok | 136 | 1860 | 2530 | 16.4 | pass |
| `i_27d35bf2cd22d3769a` | 332 | ok | 49814 | 1367 | 2510 | 16.5 | pass |
| `i_3b971612ce637e324b` | 476 | ok | 128 | 1719 | 2540 | 16.4 | pass |
| `i_a7373a7648d6ddce67` | 284 | ok | 40568 | 1150 | 2520 | 16.2 | pass |
| `i_97504cfbf824b0eeee` | 380 | ok | 54787 | 1337 | 2560 | 16.5 | pass |
| `i_f4bba5cb9d71569f25` | 2 | ok | 70 | 20 | 30 | 16.0 | pass |
| `i_4f87def68141976d87` | 48 | ok | 6659 | 215 | 1030 | 15.9 | pass |
| `i_cf46e9e6258788de2a` | 320 | ok | 58666 | 2571 | 110 | 15.9 | pass |
| `i_91a2e8f7679a6871f4` | 428 | ok | 120 | 1735 | 2540 | 16.3 | pass |
| `i_299ba50f55c486ec71` | 16 | ok | 1720 | 75 | 80 | 16.0 | pass |
| `i_9e24f6f61fea4413ac` | 256 | ok | 78170 | 93 | 150 | 16.1 | pass |
| `i_9cf7bcb5fe8c0fdac3` | 36 | ok | 5471 | 183 | 1000 | 15.9 | pass |
| `i_6421fda8c234f4ca23` | 18 | ok | 2617 | 95 | 30 | 15.9 | pass |
| `i_6bf2ce5fc66d4bad9e` | 3 | infeasible | - | - | 40 | 15.9 | pass |
| `i_8d29a9554dd222d976` | 476 | ok | 71386 | 1612 | 2610 | 16.4 | pass |
| `i_57be790be38419e246` | - | invalid | - | - | 100 | 15.9 | pass |
| `i_354f04e366ba47a0e5` | 3 | infeasible | - | - | 80 | 15.9 | pass |
| `i_dfcebb3746dc9feecb` | 332 | ok | 49814 | 1367 | 2530 | 16.3 | pass |
| `i_b05b69c48293a3d4b4` | 476 | ok | 73602 | 1953 | 2540 | 16.3 | pass |

Wall time is rounded to the nearest 10 ms and peak RSS is converted from KiB to MiB with one decimal. The unrounded values are in `benchmark_results.json`.

| Figure | Value |
|---|---|
| Maximum wall time over all 28 requests | 2699.8 ms |
| Valid feasible requests with at least 250 active cards | 15 |
| p95 wall time over those requests, nearest rank | 2699.8 ms |
| Maximum peak RSS over those requests | 16892 KiB (16.5 MiB) |

With 15 requests in scope the nearest-rank p95 is the largest value. The p95 is above 750 ms and the maximum RSS is under 64 MiB.

Certificates on the two profile requests. The gap is `(U - utility * scale) / (utility * scale)`:

| id | `U` | `scale` | utility | gap | `100 * U <= 105 * utility * scale` |
|---|---|---|---|---|---|
| `i_cf46e9e6258788de2a` | 1759980 | 30 | 58666 | 0.00% | True |
| `i_9e24f6f61fea4413ac` | 78170 | 1 | 78170 | 0.00% | True |

Consistency on the three public pairs that present the same problem twice (`L` and `H` are the lower and higher utility of the pair):

| Pair | `L` | `H` | `200 * (H - L) <= H` |
|---|---|---|---|
| `i_d377627acc7b53786a` / `i_b05b69c48293a3d4b4` | 73602 | 73602 | True |
| `i_613d784770e53c543d` / `i_91a2e8f7679a6871f4` | 120 | 120 | True |
| `i_27d35bf2cd22d3769a` / `i_dfcebb3746dc9feecb` | 49814 | 49814 | True |

Run of 2026-10-11 14:10 PDT. Recorder `environment.python`: `3.11.17 (main, Oct  6 2026, 02:08:45) [GCC 14.2.0]`. `platform`: `Linux-6.12.54-linuxkit-aarch64-with-glibc2.41`. `cpu_capacity`: `{"affinity_cpus": [0, 1, 2, 3, 4, 5, 6, 7], "cgroup_cpu_max": "200000 100000", "logical_cpus": 8, "quota_vcpus": 2.0}`.

<!-- END MEASURED -->

These are the results of the second of two runs of the unchanged recorder on the same source that day. The first run was taken while the host was running other jobs (load average about 43). Its statuses and utilities were identical; only the timing differed, with one large request at 3.84 s. The shipped `benchmark_results.json` and `benchmark_run.log` are from the second run only.

## Measurement environment

| Item | Value |
|---|---|
| Container image | `python:3.11-slim` |
| Python | 3.11, from the image. The exact version string is the recorder's `environment.python`, quoted in Results |
| Platform | linux/arm64, Docker Desktop on an Apple-silicon Mac |
| CPU limit | `--cpus=2`. The recorder stores the cgroup quota as `cpu_capacity`, quoted in Results, and `check_results.py` asserts a quota of 2 vCPUs |
| Logical CPUs visible in the container | More than 2. See `cpu_capacity` in Results |
| Network | `--network none` |
| Memory limit | None on the container. The recorder measures peak RSS per request |
| Recorder | `benchmark_runner.py`, unchanged, SHA-256 `87694477eca9636ed78766d4473821befb9d388bf2444b2e1b5310f5e6ca5943` |
| Corpus | `benchmark_inputs.json`, unchanged, SHA-256 `164ea460ed919a4e5e365c5357b9d53606f8f5fb53df8c238664c8117eae541c` |

The 2-vCPU envelope is met by the cgroup quota, not by the visible CPU count. No restriction beyond `--cpus=2` and `--network none` was applied. The recorder's environment block, input, runner and entry-point hashes, and the before and after inventories of the Python sources are in `benchmark_results.json` as the recorder wrote them.

## Measured and not measured

| Statement | Basis |
|---|---|
| Per-request status, selected set, utility, tokens, wall time and peak RSS on the 28 public requests | Measured by the recorder in the environment above |
| Legality of every recorded `ok` response, and correctness of the recorded `invalid` and `infeasible` statuses | Recomputed by `tools/check_results.py` with the independent checker |
| Exact maximum utility up to 18 active cards on the corpus and on generated requests | Tested against the brute-force oracle |
| Maximum utility on the three mid public requests (36, 48 and 64 active cards) | Equal to optima proven by long exact runs outside the time limit (5,471, 6,659, 8,606) |
| Exact maximum utility at 19 to 24 active cards | The public corpus stops at 18 active cards. The test suite compares 12 generated requests of 19 to 22 active cards with the brute-force oracle through the pipeline, and 12 requests of 23 and 24 active cards against brute-forced reduced cores whose optimum is preserved by construction (`tests/test_differential.py`). `tests/test_exact.py` adds 25 independently verified 24-card cases. Not verified: arbitrary 23 and 24-card requests have no full brute-force check, because 2^24 subsets is too slow in the oracle. There the result rests on the branch and bound exhausting its search space (`proven=True` on stderr) |
| 99% of the comparison utility on larger requests | Not measured. No public comparison utilities exist, so the 99 percent bar cannot be measured here. What stands in for it: legality from the independent checker on every public request, oracle agreement on small generated requests, a result never below the greedy construction, proven optimality on profile requests, and the repeat runs described under "Large-request search" |
| Behavior on x86-64 | Not measured. There was no x86 run. The recorded run is arm64 |
| Behavior in any deployment environment | Not verified. No deployment environment was available |

## Optional capabilities

| Capability | Decision | Notes |
|---|---|---|
| Utility upper-bound certificate | Provided on certificate-profile requests only | Omitted when the 5% test does not hold for the returned set, so a response never carries a loose certificate. Both public profile requests carry a certificate that passes the 5 percent test. See Results |
| 750 ms p95 with 64 MiB maximum RSS | Declined | Large requests outside the profile use their search time up to the 2.5 s deadline by design, so p95 is far above 750 ms. Maximum RSS is well under 64 MiB. Both figures are in Results |
| 99.5% target | Not claimed | It cannot be measured without the comparison utilities, and nothing is done differently for it |
| Consistency across equivalent requests | A tested target, not a guarantee | All three public repeat pairs returned equal utilities in the recorded run. The search is time-bounded and randomized, so equality is observed, not guaranteed. See Results |

## Limitations

- Above 24 active cards the solver is not deterministic across runs. The search is seeded, but it stops on the wall clock, so the number of moves, and with it the selected set and its utility, depends on machine speed and load. Renaming or reordering an equivalent request also changes the search path.
- Above 64 active cards and outside the certificate profile there is no optimality proof and no upper bound. The answer is the best legal set the search found in its time.
- The search quality above 64 active cards depends on how many moves fit before the deadline. On a much slower or heavily loaded host fewer moves fit, and a weaker result than the recorded one is possible.
- On a constructed 500-card request with a replacement barrier, the annealing schedule stayed at about 93 percent of a known feasible optimum. A hidden request with that shape could miss the 99 percent target.
- From 25 to 64 active cards the answer is proven optimal only when the exact pass finishes before 2.5 s. Otherwise it is the best set found.
- At 24 or fewer active cards the answer is exact only when the branch and bound finishes before 3.5 s. If it does not, the response is still `ok` and legal, and the stderr line shows `proven=False`. The response itself does not carry that flag.
- A hidden request can be harder than any public one. The contract bounds every input structure but promises nothing about topology, and the public corpus is small.
- Deadlines are fixed constants chosen for the 5 second limit in the measured container. On a much slower machine the margin between the 3.5 s deadline and the 5 s limit shrinks. The exact search reads the clock about once per 4,096 card visits and the annealing once per move.
- The hard guard at 4.0 s needs `signal.setitimer`, which Windows does not have; there only the cooperative deadlines apply. The guard interrupts Python code that ignores its deadline. It cannot help a process the host does not schedule, and what it interrupts still has to write its answer before 5 s.
- The certificate bound ignores requirements, groups, pairs and mandatory choices, as the contract defines it. It is provided only where those are absent.
- The `internal error` paths described under Fallback would answer `invalid` for a valid request.

## How this was built

The work followed [HVE for Claude Code (hve-claude)](https://github.com/kevrcress/hve-claude), a Hypervelocity Engineering method adapted from Microsoft's hve-core. The method separates four phases: Research, Plan, Implement, Review. Each phase writes a durable file, and the next phase reads that file from disk, not from chat. Each separation has a purpose. The research phase cannot write code, so it works toward verified facts. The plan fixes interfaces and file ownership before any code exists. The review validates the result against the plan.

**Orchestration.** One Claude Code session acted as orchestrator. It split the plan into 11 phases with declared dependencies and owned files, and gave each phase to a separate agent (worker subagents and peer sessions), each in its own git worktree. It verified every delivery itself before the merge: it re-ran each test gate and cross-checked modules against an independent oracle. The orchestrator did not write product code.

**Review.** The process, and what the record shows: each implementation phase was opened as its own pull request and reviewed by a second model (OpenAI Codex). Findings were fixed or declined with the reason recorded on the pull request, and the owner merged them. Three examples, which can be checked in the tracking folder and the pull request history: the validation review led to rejecting lone surrogates in text and to a reasoned decline of rejecting `-0`; the harness review hardened the result-verification tooling; the pipeline review added a hard time guard.

**Independent cross-checks.** The public corpus ships no expected outputs. Two things stand in for them: the legality checker and the brute-force oracle in `tests/`, which share no code with the solver, and 102 reference scenarios with expected answers written in a separate session (`tests/data/reference_scenarios.json`).

**The tracking folder.** `.claude-hve-tracking/` holds the files the phases handed to each other. Paths in the table are relative to that folder.

| Path | What it is |
|---|---|
| `research/2026-10-11/director-context-picker.md` | Verified findings: requirements matrix, recorder behavior, corpus census, ambiguities and their safest reading |
| `plans/2026-10-11/director-context-picker-plan.md` | The 11 phases, their dependencies, the optional-capability decisions, and the requirements added during the work |
| `plans/logs/2026-10-11/director-context-picker-log.md` | Planning discrepancies and design decisions, including the plan validator's findings |
| `details/2026-10-11/director-context-picker-details.md` | The binding module interfaces the parallel phases coded against |
| `changes/2026-10-11/director-context-picker-changes.md` | What each phase did as of packaging, with test counts and deviations |
| `reviews/rpi/2026-10-11/` | The review log (`director-context-picker-review.md`) and eight validation reports |

Start with the plan, then read the changes log. Citations of the form `file:line` are snapshots as of the date in the path and may be off by a few lines after later edits.

The tracking files are working records written under a deadline. Where a later step proved an earlier statement wrong, the file carries a dated correction, not a silent rewrite.

The tracking folder holds the summaries. The full discussion (issue comments, review text, inline comments) is on GitHub, at the links in the next two subsections.

### Repository, issues and pull requests

| What | Link | What it holds |
|---|---|---|
| Repository | <https://github.com/kevrcress/OpenArtContextPicker> | Source history; the ZIP is built from it |
| Issues | <https://github.com/kevrcress/OpenArtContextPicker/issues?q=is%3Aissue> | One parent issue and one issue per plan phase (11), each with the files the phase owns, its success criteria, and comments recording who claimed it, what was delivered and the gate result |
| Pull requests | <https://github.com/kevrcress/OpenArtContextPicker/pulls?q=is%3Apr> | One per phase plus three follow-ups; each carries the external review and a disposition comment |

### Pull requests and their reviews

Each pull request was reviewed by a second model, OpenAI Codex, which posted its findings on the pull request; each finding was either fixed on the branch or declined with the reason recorded there.

| PR | What it adds | Codex review and outcome |
|---|---|---|
| [14](https://github.com/kevrcress/OpenArtContextPicker/pull/14) | Phase 1: strict input validation (`dcp_validate.py`) | Two findings. Lone surrogates in card text accepted: fixed. `-0` accepted as integer zero: declined with the contract clause; the re-review agreed. |
| [13](https://github.com/kevrcress/OpenArtContextPicker/pull/13) | Phase 2: bitmask model and legality core (`dcp_model.py`) | No findings; the reviewer compared 3,000 generated requests against its own checker. |
| [15](https://github.com/kevrcress/OpenArtContextPicker/pull/15) | Phase 3: independent legality checker, brute-force oracle, request generators (`tests/`) | Three rounds. The generator accepted out-of-range arguments and overflowed on a huge budget ratio: both fixed. No checker bypass or oracle disagreement found. |
| [17](https://github.com/kevrcress/OpenArtContextPicker/pull/17) | Phase 4: packaging, Docker benchmark harness, result checker (`tools/`) | Three rounds. Round 1: 2 Critical, 3 Major, 1 Minor in the verification tooling, all fixed. Round 2: four items still open plus one new Major, all fixed. Round 3: one Major about how the optional consistency verdict treats "retained main quality", declined in code and stated under Limitations. |
| [18](https://github.com/kevrcress/OpenArtContextPicker/pull/18) | Phase 5: exact search for 24 or fewer active cards (`dcp_exact.py`) | No Critical or Major; bounds and branching checked against exhaustive enumeration on about 53,000 requests. Two Minor test gaps fixed (25 independently verified 24-card cases, cutoff assertions). |
| [19](https://github.com/kevrcress/OpenArtContextPicker/pull/19) | Phase 6: search for larger requests (`dcp_search.py`) | First delivery was reworked before review because results varied between runs. Review of the rework: no illegal result or bookkeeping error; one Critical (a possible overrun of tens to hundreds of milliseconds on a 500-card requirement cycle) and three Major (a constructed barrier instance at 93 percent of a known optimum; two test gaps), declined for this submission and stated under Limitations. |
| [16](https://github.com/kevrcress/OpenArtContextPicker/pull/16) | Phase 7: exact knapsack and certificate for the certificate profile (`dcp_profile.py`) | No Critical or Major; 5,000 random profile requests legal, optimal and with valid certificates. One Minor test gap fixed. |
| [20](https://github.com/kevrcress/OpenArtContextPicker/pull/20) | Phase 8: CLI, pipeline and end-to-end regression (`context_solver.py`, `dcp_pipeline.py`) | Round 1: 4 Critical and 2 Major, all fixed (no draining of oversized stdin, hard 4.0 s time guard, guarded response construction, non-zero exit when stdout cannot be written, wall-time assertions, exactness tests at 19 to 24 active cards). Re-review: two further findings that need stdin withheld for four seconds or `json.dumps` to fail, declined as unreachable in a real invocation. |
| [21](https://github.com/kevrcress/OpenArtContextPicker/pull/21) | Phase 10: this README | 4 Major and 2 Minor accuracy findings, all fixed. |
| [22](https://github.com/kevrcress/OpenArtContextPicker/pull/22) | Follow-up: tests find the supplied files at the package root | No issues. |
| [23](https://github.com/kevrcress/OpenArtContextPicker/pull/23) | Follow-up: reject structurally impossible input before parsing | No Critical or Major; the reviewer found no valid request that trips a cap. One Minor test gap, not fixed. |

Phases 9 (the recorded run) and 11 (this package) produce data and an archive, not code, and have no pull request. The repository's default branch also holds the tracking files, which were committed directly.

## Operational note

**Integrating the picker.** The picker is one call before each Director turn: after the caller has assembled the session's cards and before the prompt is rendered. It reads only the request. It carries no state from one call to the next, opens no network connection and calls no model, so it can run as a subprocess or be imported in-process. `dcp_pipeline.run(raw_bytes, t0)` is the function the command-line program itself calls: it takes the raw request bytes and a `time.perf_counter()` value from which every deadline is measured, and returns the response as a dict. In-process, make one call at a time, read the diagnostic fields from `dcp_pipeline.LAST_DIAG`, and note that the hard time guard is a `SIGALRM` handler that can be armed on the main thread only.

1. **Build the request.** `versions` and `head` come from the session's branch state. Each entry of `cards` carries `tokens` as measured by the caller's tokenizer for the text exactly as it will be rendered, and `covers` naming the entries of `features`, which holds the weights. `mandatory` lists the decisions that must always be present. `contradictions` and each card's `conflict_group` come from whatever system detects conflicts. `budget` is the tokens left for memory after the caller has subtracted everything else in the prompt, because the picker counts card tokens only.
2. **Call it.** Run `python3.11 context_solver.py` with the request on stdin. The answer is one JSON line on stdout, diagnostics go to stderr, and the exit code is 0 whenever a response line was written.
3. **Budget the time.** Enforce a caller-side timeout. The contract's limit is 5 s and the picker's own hard guard is at 4.0 s. Requests of at most 24 active cards and requests in the certificate profile returned in a fraction of a second in the recorded run. Above 64 active cards outside the profile a call takes about 2.5 s by design, because the search runs until its deadline; from 25 to 64 it takes between about 1 s and about 2.5 s (see Results). If a turn cannot spend that, the deadlines are two constants in `dcp_pipeline.py`, `MID_SEARCH_DEADLINE_S` and `LARGE_DEADLINE_S`. Lowering them trades quality for time, and that trade is not measured here.
4. **Use the answer.** Render the texts of `selected` in the caller's own order: the response carries ids only, sorted by id in ASCII order, which is not a narrative order. `covered`, `utility` and `tokens` are for logging. The outcome table below says how to handle `invalid`, `infeasible` and no answer.
5. **Roll it in.** Run it in shadow first: compute the selection, log it, and keep sending the current context. Compare the selection against what the current context builder sends. Keep the stderr diagnostic line (`method`, `active`, `proven`, `elapsed_ms`) together with a hash of the request for later analysis. Pin Python 3.11. There are no dependencies to install.

These are suggestions from the component's side. The session store, the extractor, the tokenizer and the prompt renderer are the caller's, and nothing here describes how OpenArt's systems work today.

**Bad upstream metadata.** A request that breaks the input contract is rejected as `invalid` with a reason. The picker never repairs it: it does not drop an unknown reference, deduplicate a pair, clamp a range, infer a contradiction from text or redirect a requirement to a newer card. A structurally valid request whose metadata is wrong (a missing contradiction pair, a wrong supersession link, a wrong weight or token count) cannot be detected here and produces a legal answer to the wrong problem. Detection of that belongs upstream, with the extractor.

**Safe fallback for the caller.** The caller should treat each outcome separately:

| Outcome | Meaning | Suggested handling |
|---|---|---|
| `ok` | A legal set under the supplied metadata | Use `selected`. Totals are recomputable from it |
| `invalid` | The request broke the input contract, or an internal error occurred | Do not send a guessed selection. Log the reason, fix the request upstream, and continue the turn with a context the caller already knows to be safe |
| `infeasible` | The mandatory cards cannot form a legal set | The picker does not choose which mandatory card to drop. That decision belongs to the caller or the user |
| Timeout, non-zero exit, empty or unparseable stdout | No answer | Enforce a caller-side timeout, treat it like `invalid`, and alert |

A context "known to be safe" is a product decision. This component does not supply one beyond the mandatory closure it returns inside an `ok` response.

**Limits of the union-coverage objective.** Utility is the summed weight of covered features. It does not measure:

- Model obedience: whether the model follows the selected cards.
- Rendering overhead: tokens spent on formatting, separators and instructions around the cards. The budget counts card tokens only.
- Semantic nuance: two cards covering the same feature count as equal, and `text` is never read.
- Output continuity: whether consecutive turns receive similar context. Each request is solved alone, and above 24 active cards two runs can differ.
- Production drift: weights, token counts and card shapes that change over time.
- A conflict the extractor omitted: a real contradiction that is not in the request as a group or a pair is not enforced.

**Scope of the evidence.** The extractor, the feature weights and the tokenizer are assessment assumptions supplied with the task. The corpus is synthetic, and the 250 to 500 active-card workload is an assessment requirement, not a measured production distribution. Nothing here is a statement about OpenArt's production systems, customers, latency or failure rates.
