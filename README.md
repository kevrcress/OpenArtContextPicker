# Director context picker

A Python 3.11 standard-library command-line program that chooses which memory cards go into the prompt for one Director turn. It reads one JSON request on stdin and writes one JSON response line on stdout, following the supplied context request contract.

The selection is a legal set of cards (visible from the head version, not superseded, requirements closed, one card per conflict group, no contradiction pair, within the token budget, all mandatory cards included) that maximizes the summed weight of the features the selected cards cover.

Numbers marked `TBD-MEASURED` are filled in from the recorded benchmark run. Nothing in this file marked as measured was estimated.

## Package layout

All paths are relative to the archive root. Every command below is run from that root.

| Path | Purpose |
|---|---|
| `context_solver.py` | Entry point: stdin request, stdout response, exit code 0 |
| `dcp_validate.py` | Strict input validation |
| `dcp_model.py` | Active set, requirement closures, conflict masks, legality test |
| `dcp_exact.py` | Exact branch and bound |
| `dcp_profile.py` | Exact knapsack and upper-bound certificate for the certificate profile |
| `dcp_search.py` | Greedy construction and local search for large requests |
| `dcp_pipeline.py` | Dispatch, deadlines, fallback, response assembly |
| `tests/` | Regression tests, an independent checker, a brute-force oracle, request generators |
| `tools/` | Recorded-run script, results checker, packaging scripts |
| `benchmark_runner.py` | The supplied recorder, unchanged |
| `benchmark_inputs.json` | The supplied public corpus (28 requests), unchanged |
| `director_session.json` | The supplied sample session, unchanged |
| `benchmark_results.json`, `benchmark_run.log` | Output of the recorded run, exactly as the recorder wrote it |

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

Run the local regression suite (about 100 seconds on the development machine; it needs no Docker and no network):

```sh
python3.11 -m unittest discover -s tests
```

Check the shipped recorded results against the corpus with the independent checker, and print the per-instance table and the summary figures:

```sh
python3.11 tools/check_results.py .
```

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

`tools/build_package.py` and `tools/make_zip.py` produced this archive from the development repository. `build_package.py` reads the supplied files from the repository layout and is not meant to be run from the extracted archive.

## Method

### Process boundary (`context_solver.py`)

The entry point records `time.perf_counter()` before any other import; every deadline below is measured from that moment. It reads at most 16 MiB plus one byte from stdin and discards the rest, writes exactly one JSON line to stdout, writes one diagnostic line to stderr (`method`, `active`, `proven`, `elapsed_ms`), and always exits 0. If anything fails before a response exists, it prints `{"status":"invalid","reason":"internal error"}`.

### Validation (`dcp_validate.py`)

The request is rejected as `invalid`, with a short ASCII reason, when it breaks any input rule of the contract. Nothing is repaired, defaulted or dropped. Checks include: size at most 16 MiB (`MAX_BYTES`), strict UTF-8, no byte order mark, exactly one JSON object with nothing after it, no duplicate object keys, no fractional, exponent or non-finite numbers, booleans not accepted as integers, exactly the seven top-level keys, exact key sets for versions and cards (`text` optional), identifier syntax, every count and range limit in the contract table, unique IDs, existing references, an acyclic version graph, supersession only over a strict ancestor version, and distinct unordered contradiction pairs with no self-pair. Validation runs before any feasibility test, so `invalid` takes precedence over `infeasible`.

### Model (`dcp_model.py`)

`build_problem` computes the versions visible from `head`, the active cards (visible and not superseded by a visible card, directly or through a chain), and for each active card its transitive `requires` closure, the cards it conflicts with (same conflict group or a contradiction pair), and the features it covers. Cards are bits of Python integers. A card whose closure leaves the active set, contains a conflict, or cannot be added to the mandatory closure is not usable. The request is `infeasible` only when the mandatory closure itself is not a legal set: a mandatory card that is not active, a requirement on a card that is not active, a group clash or contradiction pair inside the closure, or a closure above the budget. `is_legal` is the single legality test every solver result passes through.

### Dispatch (`dcp_pipeline.py`)

| Condition, tested in this order | Method | Deadline after process start | Constant |
|---|---|---|---|
| Request is in the certificate profile | Exact 0/1 knapsack, then a certificate | 2.5 s | `LARGE_DEADLINE_S` |
| At most 24 active cards | Exact branch and bound | 3.5 s | `EXACT_MAX_ACTIVE`, `EXACT_DEADLINE_S` |
| 25 to 64 active cards | Local search until 1.0 s, then exact branch and bound seeded with that result until 2.5 s | 1.0 s, 2.5 s | `MID_EXACT_MAX_ACTIVE`, `MID_SEARCH_DEADLINE_S`, `LARGE_DEADLINE_S` |
| More than 64 active cards | Greedy construction and local search | 2.5 s | `LARGE_DEADLINE_S` |

The active-card count is the contract's count: after visibility and supersession, before unusable cards are removed. If the profile solver cannot finish in time, the request falls through to the size-based rows.

### Exact search (`dcp_exact.py`)

Depth-first branch and bound over the usable cards. Each node either takes a card together with its whole requirement closure or excludes the card and everything that depends on it. Two upper bounds prune: a fractional knapsack over the remaining cards' own gains and tokens, and the weight of the features the remaining cards can still reach. Both bounds ignore constraints, so they never cut off a better legal set. The search starts from a greedy solution. When the search space is exhausted before the deadline, the result is a maximum-utility legal set and the stderr line shows `proven=True`. When the deadline arrives first, the best legal set found so far is returned and the line shows `proven=False`.

### Certificate profile (`dcp_profile.py`)

The profile is the one the contract defines: every card of the request has an empty `requires` and a null `conflict_group`, `contradictions` is empty, and no feature is covered by more than one active card. Card values are then additive, and the problem is a 0/1 knapsack with the mandatory cards forced. `solve_profile` solves it exactly by dynamic programming over the token budget.

`build_certificate` sets each feature price to `weight * scale` and tries a small set of budget prices: zero, and the value per token of the card at which a fractional greedy fill crosses the budget and of its two neighbors. It keeps the price with the smallest bound `U` and returns the certificate only when `100 * U <= 105 * utility * scale` holds for the set actually returned. Otherwise the response carries no certificate. A response outside the profile never carries one.

### Large-request search (`dcp_search.py`)

TBD-SEARCH: this module was being reworked when this section was written. The text describes the file as it was then and has to be refreshed against the shipped file.

`solve_large` builds three greedy solutions on top of the mandatory closure, each adding one card with its closure at a time: best gain per added token, best gain per card that the addition would block, and best plain gain. It keeps the best of the three. Local search then runs in three slices of the remaining time: from the per-token solution, from the per-blocked-card solution, and for the rest of the time from the best set seen. One move picks a random usable card that is not selected, removes the selected cards that conflict with it together with their dependents, adds the card's closure, sheds sampled cards with the least lost weight per freed token while the set is over budget, and refills greedily. A move that lowers utility is undone. After a run of moves without improvement (between `STALE_MIN` 120 and `STALE_MAX` 600), the search returns to the best set, removes 2 to 5 random units and refills without them. The random generator is seeded with a fixed value (`DEFAULT_SEED`), and the search stops at its deadline.

### Fallback (`dcp_pipeline.py`)

Once the model exists, every failure still produces an `ok` response with a legal set. An exception in a solver is written to stderr and the best legal set found so far is kept. A result is accepted only if `is_legal` passes and its utility is not below the current best. The floor is the mandatory closure, which is legal by construction. The final set is checked with `is_legal` once more before the response is built.

Two paths answer `invalid` for a request that may be valid: an unexpected exception inside validation (`internal error`), and an unexpected exception while building the model (`internal error: model construction failed`). Both would be wrong answers for a valid request. They exist so that the process still returns one well-formed line. Tests force both paths; neither was observed on a valid request.

## Tests

The regression command runs everything in `tests/`.

| File | What it shows |
|---|---|
| `checker.py` | Independent legality and response checker written from the contract. It imports nothing from the solver |
| `oracle.py` | Brute-force maximum utility by subset enumeration, independent of the solver |
| `gen.py` | Seeded generators: random valid requests, contract-maximum requests, renamed and shuffled equivalent copies |
| `test_checker_oracle.py` | The checker, oracle and generators against hand-derived values |
| `test_validate.py` | One accepting and one rejecting case for every input rule |
| `test_model.py` | Visibility, supersession, closures, conflicts, feasibility, legality |
| `test_exact.py` | Exact search against the oracle, 24-card stress families, deadline behavior |
| `test_profile.py` | Profile detection, exact knapsack against the oracle, certificate validity and the 5% test |
| `test_search.py` | Large search: legality, quality against the oracle on small requests, return within 50 ms of the deadline, never below the greedy result |
| `test_differential.py` | 320 generated requests (1 to 14 active cards) through the pipeline against the checker and oracle, and single-rule mutations that must be `invalid` |
| `test_cli.py` | The process contract (one line, exit 0, any working directory, oversize and garbage input), every fallback path, and contract-maximum requests |
| `test_corpus.py` | The 28 public requests through the CLI: checker verdict for each, oracle equality up to 18 active cards, certificates on profile requests and none elsewhere, host wall time, consistency reported |
| `test_reference_scenarios.py` | 102 hand-written scenarios (38 `ok`, 8 `infeasible`, 56 `invalid`) through the CLI |
| `test_tools.py` | The packaging and results tools, without Docker |

## Results on the public corpus

Source: `benchmark_results.json` and `benchmark_run.log`, written by the unchanged recorder in the environment described below, and summarized by `python3.11 tools/check_results.py .`. Every request is listed, including invalid, infeasible, failed and timed-out ones.

Status counts: `ok` TBD-MEASURED, `invalid` TBD-MEASURED, `infeasible` TBD-MEASURED. Failed or timed-out requests: TBD-MEASURED.

| id | active cards | status | utility | tokens | wall_ms | peak_rss_kib | timed_out | checker verdict |
|---|---|---|---|---|---|---|---|---|
| TBD-MEASURED | TBD-MEASURED | TBD-MEASURED | TBD-MEASURED | TBD-MEASURED | TBD-MEASURED | TBD-MEASURED | TBD-MEASURED | TBD-MEASURED |

Summary over valid feasible requests with at least 250 active cards (the contract's efficiency scope):

| Figure | Value |
|---|---|
| Requests in scope | TBD-MEASURED |
| p95 wall time, nearest rank | TBD-MEASURED ms |
| Maximum peak RSS | TBD-MEASURED KiB |
| Maximum wall time over all 28 requests | TBD-MEASURED ms |

Certificates on profile requests:

| id | `U` | `scale` | utility | `100 * U <= 105 * utility * scale` |
|---|---|---|---|---|
| TBD-MEASURED | TBD-MEASURED | TBD-MEASURED | TBD-MEASURED | TBD-MEASURED |

Consistency on the three public pairs that present the same problem twice (`L` and `H` are the lower and higher utility of the pair):

| Pair | `L` | `H` | `200 * (H - L) <= H` |
|---|---|---|---|
| `i_d377627acc7b53786a` / `i_b05b69c48293a3d4b4` | TBD-MEASURED | TBD-MEASURED | TBD-MEASURED |
| `i_613d784770e53c543d` / `i_91a2e8f7679a6871f4` | TBD-MEASURED | TBD-MEASURED | TBD-MEASURED |
| `i_27d35bf2cd22d3769a` / `i_dfcebb3746dc9feecb` | TBD-MEASURED | TBD-MEASURED | TBD-MEASURED |

## Measurement environment

| Item | Value |
|---|---|
| Container image | `python:3.11-slim` |
| Python | 3.11.17 |
| Platform | linux/arm64, Docker Desktop on an Apple-silicon Mac |
| CPU limit | `--cpus=2`; the recorder stored `cgroup_cpu_max "200000 100000"` and `quota_vcpus 2.0` |
| Logical CPUs visible in the container | 8 |
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
| Exact maximum utility at 19 to 24 active cards | Not verified by brute force: exactness at 19 to 24 active cards has no brute-force oracle. It rests on the branch and bound exhausting its search space (`proven=True` on stderr) |
| 99% of the comparison utility on larger requests | Not measured. No public comparison utilities exist, so the 99 percent bar cannot be measured here. What stands in for it: legality from the independent checker on every public request, oracle agreement on small generated requests, a result never below the greedy construction, and proven optimality on profile requests |
| Behavior on x86-64 | Not measured. There was no x86 run. The recorded run is arm64 |
| Behavior in any deployment environment | Not verified. No deployment environment was available |

## Optional capabilities

| Capability | Decision | Notes |
|---|---|---|
| Utility upper-bound certificate | Provided on certificate-profile requests only | Omitted when the 5% test does not hold for the returned set, so a response never carries a loose certificate. Recorded result: see the certificate table |
| 750 ms p95 with 64 MiB maximum RSS | Declined | Large requests outside the profile use their search time up to the 2.5 s deadline by design. Measured anyway: p95 TBD-MEASURED ms, maximum RSS TBD-MEASURED KiB |
| 99.5% target | Not claimed | It cannot be measured without comparison utilities, and nothing is done differently for it |
| Consistency across equivalent requests | A tested target, not a guarantee | Result on the public pairs: TBD-MEASURED of 3 pairs satisfy `200 * (H - L) <= H`. See the consistency table |

## Limitations

- Above 24 active cards the solver is not deterministic across runs. The search is seeded, but it stops on the wall clock, so the number of moves, and with it the selected set and its utility, depends on machine speed and load. Renaming or reordering an equivalent request also changes the search path.
- Above 64 active cards and outside the certificate profile there is no optimality proof and no upper bound. The answer is the best legal set the search found in its time.
- From 25 to 64 active cards the answer is proven optimal only when the exact pass finishes before 2.5 s. Otherwise it is the best set found.
- At 24 or fewer active cards the answer is exact only when the branch and bound finishes before 3.5 s. If it does not, the response is still `ok` and legal, and the stderr line shows `proven=False`. The response itself does not carry that flag.
- A hidden request can be harder than any public one. The contract bounds every input structure but promises nothing about topology, and the public corpus is small.
- Deadlines are fixed constants chosen for the 5 second limit in the measured container. On a much slower machine the margin between the 3.5 s deadline and the 5 s limit shrinks. The exact search reads the clock about once per 4,096 card visits and the local search once per move.
- The certificate bound ignores requirements, groups, pairs and mandatory choices, as the contract defines it. It is provided only where those are absent.
- The two `internal error` paths described under Fallback would answer `invalid` for a valid request.

## Operational note

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
