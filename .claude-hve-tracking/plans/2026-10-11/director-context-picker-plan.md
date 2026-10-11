# Implementation Plan: Director context picker (`director-context.zip`)
Date: 2026-10-11
Task slug: director-context-picker
Research: .claude-hve-tracking/research/2026-10-11/director-context-picker.md
Details: .claude-hve-tracking/details/2026-10-11/director-context-picker-details.md
Status: Approved (2026-10-11 12:53 PDT; the owner's kick-off delegated plan decisions: "Otherwise decide and record the decision in the plan")

## Overview

Build a flat set of Python 3.11 standard-library modules behind `context_solver.py`: strict validation, a bitmask model of the legal-set rules, an exact branch and bound for 24 or fewer active cards, an exact knapsack with certificate for the certificate profile, and a greedy plus local search for everything larger, with the mandatory closure as the always-legal fallback. Correctness is checked by an independent legality checker and brute-force oracle written in `tests/`, because the corpus has no expected outputs. The recorded run happens once, last, in Docker at 2 vCPUs from a clean extraction; then the README numbers are filled and the ZIP is built and re-verified.

Deadline: ZIP due 15:30 PDT; target 14:45. Plan written 12:41 to 12:55 PDT.

## Decisions on optional capabilities

| Capability | Decision | Reason |
|---|---|---|
| Utility upper-bound certificate | **Yes**, on certificate-profile requests only | The profile is a plain 0/1 knapsack; exact DP plus the LP dual price gives a gap below one card's value (research "Certificate profile"). Omitted elsewhere and omitted when the 5% test does not hold, so a response never carries a loose certificate |
| 750 ms p95 with 64 MiB RSS | **No** | Six public large instances have unit weights, where the 99% bar allows a deficit of one to four cards; search time is spent on main quality (deadline 2.5 s from process start). p95 and max RSS are still measured and reported |
| 99.5% target | **No (not claimed)** | No public comparison utility exists, so it cannot be measured. Nothing is done differently for it |
| Consistency across equivalent requests | **Yes, as a tested target** | Checked on the three public repeat pairs and on renamed and shuffled copies (`gen.permute_request`); the result is reported whether or not `200*(H-L) <= H` holds. Not guaranteed on hidden requests |

Other decisions: `benchmark_inputs.json` ships in the ZIP (922,249 bytes zipped, measured) so the clean-extraction commands and the corpus regression work from the archive alone; requests with 25 to 249 active cards are held to the 99% reading (research A-10); flat modules, no package directory.

## Plan-time checks that ran

- Container environment. Command: `docker run --rm --cpus=2 --network none python:3.11-slim sh -c 'python -V; cat /sys/fs/cgroup/cpu.max; nproc; uname -srm; ...'`. Output: `Python 3.11.17`, `200000 100000`, `8`, `Linux 6.12.54-linuxkit aarch64`.
- Recorder command, verbatim as in details section 9, run at 12:42 PDT in a scratch copy (copies of `resources/benchmark_runner.py` and `resources/benchmark_inputs.json` plus a three-line stub solver that answers `invalid`): `rc=0`; `benchmark_run.log` has 28 lines; `benchmark_results.json` has `schema openart-context-observations/2`, `inputs_sha256 164ea460…e541c`, `runner_sha256 87694477…5943`, `python_sources_unchanged True`, `cpu_capacity {'logical_cpus': 8, 'affinity_cpus': [0..7], 'cgroup_cpu_max': '200000 100000', 'quota_vcpus': 2.0}`, `invocation 'benchmark_runner.py --solution context_solver.py --inputs benchmark_inputs.json --output benchmark_results.json'`; stub wall 6.3 to 11.9 ms; `peak_rss_kib` 16232 to 16888. The recorder's RSS floor in this container is therefore about 16 MiB. The whole stub run took 5 s.
- `zip -9` of `benchmark_inputs.json`: 922,249 bytes.
- No Dockerfile is specified; the stock image is used unmodified.

## Phases

Waves: 1, 2, 3 start together. 4, 5, 6, 7 start when 2 and 3 are complete (4 needs only 3). 8 starts when 1, 4, 5, 6, 7 are complete. HVE review runs after 8. 9 and 10 follow (10 may start when 8 is complete; 9 waits for the review fixes). 11 is last.

### Phase 1: Strict input validation
Dependencies: none
Owns: `dcp_validate.py`, `tests/test_validate.py`
Estimated scope: 2 files, about 250 + 250 lines
Success criteria: `python3.11 -m unittest discover -s tests -p 'test_validate.py' -v` passes with at least one accepting and one rejecting case for every rule in details section 2, and the sample session plus a 500-card generated request validate in under 100 ms.

Steps:
- [ ] Step 1.1: Implement `InvalidRequest` and `validate_request(raw: bytes) -> dict` per details section 2.
  - Assumption: `json.JSONDecoder` hooks `object_pairs_hook`, `parse_float`, `parse_constant` behave in 3.11 as described in research "Python 3.11 parser defaults" [MEDIUM]; guard: each default is pinned by a test in step 1.2.
- [ ] Step 1.2: Tests for every rule: size limit at exactly 16 MiB and one byte over, invalid UTF-8, BOM, empty and whitespace-only input, top-level array, trailing bytes, trailing whitespace accepted, duplicate keys at top level and inside a card, `1.0`, `1e2`, `true` as integer, `NaN`, `Infinity`, 5,000-digit integer, 100,000-deep nesting, unknown and missing keys at each level, identifier pattern (empty, 65 characters, non-ASCII letter, trailing newline), every range bound in the limits table at both edges, duplicate ids and array entries, unknown references, cyclic versions, self-parent, self-supersede, supersede within one version, across unrelated branches and from a strict ancestor (valid), self-requirement (valid), requirement cycle (valid), pair shape, self-pair, duplicate pair in both orientations, `null` anywhere but `conflict_group`, `text` at 2,048 and 2,049 code points.
- [ ] Step 1.3: Run the gate `python3.11 -m unittest discover -s tests -p 'test_validate.py' -v > gate.log 2>&1; echo rc=$?`.

### Phase 2: Model and legality core
Dependencies: none
Owns: `dcp_model.py`, `tests/test_model.py`
Estimated scope: 2 files, about 220 + 250 lines
Success criteria: `python3.11 -m unittest discover -s tests -p 'test_model.py' -v` passes; the sample session yields `n == 7` with the closures and usable set from the research hand walk; `build_problem` on the largest public instance runs in under 60 ms on the host.

Steps:
- [ ] Step 2.1: Implement `Infeasible`, `Problem`, `build_problem` and the mask helpers per details section 3.
- [ ] Step 2.2: Tests: visibility through a merge head; an invisible branch; supersession chain; a visible superseder that is itself superseded; an invisible superseder that must not deactivate; `requires` on an inactive card makes the dependent unusable; requirement cycle and self-requirement closures; pair inside a closure and same group inside a closure make it unusable; pair with an inactive endpoint is inert; mandatory inactive, mandatory closure with a pair, mandatory over budget all raise `Infeasible`; empty mandatory at budget 0 is feasible; `is_legal` rejects one violation of each of the six conditions; the sample session numbers.
- [ ] Step 2.3: Timing check on `resources/benchmark_inputs.json` instance `i_3b971612ce637e324b` (read-only), recorded in the changes log.
- [ ] Step 2.4: Run the gate for `tests/test_model.py`.

### Phase 3: Independent legality checker, oracle and generators
Dependencies: none
Owns: `tests/checker.py`, `tests/oracle.py`, `tests/gen.py`, `tests/test_checker_oracle.py`
Estimated scope: 4 files, about 450 lines
Success criteria: `python3.11 -m unittest discover -s tests -p 'test_checker_oracle.py' -v` passes, including the sample-session optimum 61 and the pinned outcomes of the seven tiny public requests; none of these files imports a `dcp_*` module (checked by `grep -n "import dcp" tests/checker.py tests/oracle.py tests/gen.py` returning nothing).

Steps:
- [ ] Step 3.1: `checker.py` per details section 4, written from the contract text, with sets and dicts.
- [ ] Step 3.2: `oracle.py` exhaustive search over subsets of active cards.
- [ ] Step 3.3: `gen.py` `random_request` and `permute_request`.
- [ ] Step 3.4: Self-tests pinned to hand-derived values (details section 4), and a test that `permute_request` preserves `best_utility` on 30 generated requests.
- [ ] Step 3.5: Run the gate for `tests/test_checker_oracle.py`.

### Phase 4: Packaging and Docker benchmark harness
Dependencies: Phase 3
Owns: `tools/build_package.py`, `tools/run_recorded.sh`, `tools/check_results.py`, `tools/make_zip.py`, `tests/test_tools.py`, `.gitignore` (adds `build/`)
Estimated scope: 5 files, about 350 lines
Success criteria: with a stub `context_solver.py` in a scratch directory, `tools/run_recorded.sh` produces a 28-line `benchmark_run.log` and a `benchmark_results.json` with `quota_vcpus` 2.0, and `tools/check_results.py` exits 1 on the stub (every stub answer is wrong) and reports the integrity fields as matching; `shasum -a 256 resources/*` is unchanged afterwards.

Steps:
- [ ] Step 4.1: `build_package.py`, `run_recorded.sh`, `make_zip.py` per details section 9. `check_results.py` imports `tests/checker.py` by path at run time and asserts every item in details section 9 (integrity fields and, per record, exit code, timeout flag, parse error, raw stdout shape, wall and RSS limits, checker verdict). Add `build/` to `.gitignore`.
- [ ] Step 4.2: `tests/test_tools.py`: `build_package.py` copies a byte-identical recorder and corpus and refuses on a hash mismatch (simulated with a temp copy, never by editing `resources/`); `make_zip.py` puts files at the archive root and excludes `__pycache__`.
- [ ] Step 4.3: Stub dry run in a scratch directory under Docker; paste the command and its output into the changes log.
- [ ] Step 4.4: Confirm `resources/` hashes against the baseline after the dry run: `shasum -a 256 resources/benchmark_runner.py resources/benchmark_inputs.json`.

### Phase 5: Exact search for 24 or fewer active cards
Dependencies: Phase 2, Phase 3
Owns: `dcp_exact.py`, `tests/test_exact.py`
Estimated scope: 2 files, about 200 + 150 lines
Success criteria: on at least 300 generated requests with 1 to 16 active cards (all constraint types, including supersession and infeasible-free cases) `solve_exact` returns `proven` true and utility equal to `oracle.best_utility`; on the three public small instances and the sample session likewise; a stress set of 40 generated requests at exactly 24 active cards (unconstrained with shared features and loose budget, knapsack-tight, conflict-dense) each finish `proven` in under 1.5 s on the host.

Steps:
- [ ] Step 5.1: Implement `solve_exact` per details section 5.
- [ ] Step 5.2: Oracle comparison tests and the 24-card stress test.
  - Assumption: the fractional-knapsack and coverable-union bounds prune 24-card worst cases to under 1.5 s in pure Python [MEDIUM]; guard: the stress test in this step measures it; if any case exceeds 1.5 s, strengthen ordering or bounds before closing the phase, and record the worst time.
- [ ] Step 5.3: Run the gate for `tests/test_exact.py`.

### Phase 6: Large-instance search
Dependencies: Phase 2, Phase 3
Owns: `dcp_search.py`, `tests/test_search.py`, `tools/tune_search.py`
Estimated scope: 3 files, about 300 + 120 + 80 lines
Success criteria: every mask returned on the 18 public instances with at least 25 active cards passes `checker.check_response` when rendered as a response; on generated requests of 10 to 16 active cards the result is within 1% of `oracle.best_utility` in at least 95% of cases and always legal; on each public large instance the result at a 2.0 s search deadline (the pipeline's 2.5 s from process start leaves about that much) is at least 99% of the best of three 20 s reference runs (`tools/tune_search.py` table pasted into the changes log); the function returns within 50 ms after its deadline.

Steps:
- [ ] Step 6.1: Greedy construction and incremental cover counts per details section 6.
- [ ] Step 6.2: Ejection-and-refill local search with perturbation, deadline handling and legal fallback.
- [ ] Step 6.3: `tests/test_search.py` (legality on generated and public instances, deadline honoured, deterministic seed interface) and `tools/tune_search.py`.
- [ ] Step 6.4: Run `tools/tune_search.py` on the host; paste the table into the changes log, with the six unit-weight instances called out.
  - Assumption: local search reaches within 1% of a long reference run in 2 s of pure Python on 476 active cards [LOW]; guard: step 6.4 measures it. If any instance misses, report the shortfall in the changes log and the README; do not raise the deadline above 3.0 s.
- [ ] Step 6.5: Run the gate for `tests/test_search.py`.

### Phase 7: Certificate-profile knapsack and certificate
Dependencies: Phase 2, Phase 3
Owns: `dcp_profile.py`, `tests/test_profile.py`
Estimated scope: 2 files, about 180 + 120 lines
Success criteria: on generated profile requests of up to 16 active cards `solve_profile` equals `oracle.best_utility`; on the two public profile instances the returned certificate passes `checker.check_response` and satisfies `100*U <= 105*utility*s` computed by `checker.certificate_bound`; a generated 500-card, budget-8,192 profile request finishes in under 1.5 s on the host or returns `None`.

Steps:
- [ ] Step 7.1: `profile_applies`, `solve_profile`, `build_certificate` per details section 7.
- [ ] Step 7.2: Tests, including a profile request with a mandatory card and one with a superseded card, and a case where no tight certificate exists (returns `None`).
- [ ] Step 7.3: Record the two public instances' utility, `U/s` and gap in the changes log.
- [ ] Step 7.4: Run the gate for `tests/test_profile.py`.

### Phase 8: CLI, pipeline and corpus regression
Dependencies: Phase 1, Phase 4, Phase 5, Phase 6, Phase 7
Owns: `context_solver.py`, `dcp_pipeline.py`, `tests/test_cli.py`, `tests/test_corpus.py`, `tests/test_differential.py`
Estimated scope: 4 files, about 350 lines
Success criteria: the full regression `python3.11 -m unittest discover -s tests -v` passes; every one of the 28 public requests run through the CLI as a subprocess gets a response that passes `checker.check_response`, with the statuses from the research table (2 invalid, 2 infeasible, 24 ok) and oracle-equal utility on the three small instances; no public request takes over 3.5 s wall on the host.

Steps:
- [ ] Step 8.1: `dcp_pipeline.run` and `context_solver.py` per details section 8.
- [ ] Step 8.2: `tests/test_cli.py`: one JSON line on stdout and exit 0 for ok, invalid, infeasible, empty stdin, garbage bytes and a solver exception (injected by monkeypatching in-process); nothing but the response on stdout; runs from a different working directory.
- [ ] Step 8.3: `tests/test_corpus.py`: all 28 public requests through the CLI, checked with `tests/checker.py`; exactness against the oracle for 18 or fewer active cards; sample session equals 61; consistency ratio on the three repeat pairs and on one `permute_request` copy of a large instance (asserted as `200*(H-L) <= H`; on failure the assertion message carries L and H).
- [ ] Step 8.4: Fault-injection check of the fallback: with `solve_large` patched to raise, the response is the mandatory closure and legal.
- [ ] Step 8.4a: `tests/test_differential.py`: on at least 300 generated requests of 1 to 14 active cards, half with mandatory cards and a third with supersession (so that infeasible requests occur), `dcp_pipeline.run` on the serialized request returns `infeasible` exactly when `checker.expected_feasible` is false, and otherwise an `ok` response that passes `checker.check_response` with utility equal to `oracle.best_utility`. Also 50 invalid mutations of valid requests (one rule broken each) all return `invalid`.
- [ ] Step 8.4b: Contract-maximum run through the CLI as a subprocess: a generated valid request with 500 active cards, 10,000 pairs, 1,024 features, up to 64 covers per card, tokens up to 512, budget 8,192, 96 versions, a 200-card requires chain and a requires cycle; and a generated maximum profile request (500 cards, budget 8,192). Each response passes `checker.check_response` and wall time is under 4.0 s on the host; record both times in the changes log.
- [ ] Step 8.5: Run the full gate.
- [ ] Step 8.6: One trial of `tools/run_recorded.sh` on a scratch package built by `tools/build_package.py` (not the recorded run), then `tools/check_results.py`; record max wall, p95 and max RSS for the large workload and confirm `LARGE_DEADLINE_S` leaves every wall time under 4.0 s; lower the constant if not.
- [ ] Step 8.7: Evidence for the mid range: run `solve_exact` with a 120 s deadline on the three public mid instances (36, 48, 64 active); record whether each is proven and its utility against the CLI result. Informational; recorded in the changes log and the README, not a gate.

### Phase 9: Recorded benchmark run
Dependencies: Phase 4, Phase 8 (and the HVE review with every Critical and Major finding fixed)
Owns: `benchmark_results.json`, `benchmark_run.log`
Estimated scope: 2 generated files
Success criteria: `tools/check_results.py` on the run directory exits 0; `runner_sha256` and `inputs_sha256` equal the baseline; `python_sources_unchanged` is true; `quota_vcpus` is 2.0; 28 records; the two files in the repo root are byte-identical to the run directory's (`cmp`).

Steps:
- [ ] Step 9.1: `git status --short` is clean for every `.py`; full regression gate passes.
  - Assumption: the HVE review has run and every Critical and Major finding is fixed before this step [HIGH: owner instruction].
- [ ] Step 9.2: Build the package, zip a staging archive, extract into a new empty directory, run `tools/run_recorded.sh` there (details section 9).
- [ ] Step 9.3: Run `tools/check_results.py` there; paste its table into the changes log, listing every failed, timed-out or non-ok request.
- [ ] Step 9.4: Copy the two files into the repo root with `cp`, verify with `cmp`. Never edit them. Any later `.py` change means repeating this phase.

### Phase 10: README
Dependencies: Phase 4, Phase 8
Owns: `README.md`
Estimated scope: 1 file, about 200 lines
Success criteria: every section in details section 10 is present; every command in it was run as written and its exit code recorded in the changes log; measured numbers are marked `TBD-MEASURED` and nothing estimated is presented as measured.

Steps:
- [ ] Step 10.1: Write `README.md` from the implemented code (read the modules, not this plan) and details section 10.
- [ ] Step 10.2: Run each command in the README from a scratch copy of the package and record the result.

### Phase 11: README numbers, ZIP build and clean-extraction check
Dependencies: Phase 9, Phase 10
Owns: `README.md` (after Phase 10), `director-context.zip`
Estimated scope: 1 file edited, 1 archive
Success criteria: no `TBD-MEASURED` remains; the archive contains at its root `context_solver.py`, `benchmark_results.json`, `benchmark_run.log`, `README.md`, `benchmark_runner.py`; extracting it into a new empty directory and running the README's regression command exits 0; `tools/check_results.py` on the extraction exits 0; every `.py` hash in the extraction equals `python_sources_after` in `benchmark_results.json`; `shasum -a 256` of the extracted `benchmark_runner.py` equals the baseline.

Steps:
- [ ] Step 11.1: Fill README numbers from `tools/check_results.py` output and `benchmark_results.json` `environment`.
- [ ] Step 11.2: `tools/build_package.py`, then `tools/make_zip.py` to `director-context.zip`.
- [ ] Step 11.3: Extract into a new empty directory; run the regression command; run `tools/check_results.py`; compare `.py` hashes with `python_sources_after`; list the archive.
- [ ] Step 11.4: `git status --short` shows `director-context.zip` and `gate.log` untracked-and-ignored only.

## Risk Log

| Risk | Likelihood | Mitigation |
|---|---|---|
| Local search misses the hidden 99% comparison on unit-weight coupled instances | Medium | Spend 2.5 s per large request on search; compare against 20 s reference runs (step 6.4); report the measured shortfall honestly; decline the 750 ms option |
| A validation gap makes one hidden invalid request answer `ok`, failing a whole group | Medium | Rule-by-rule tests at both edges (step 1.2); independent checker; review dimension on validation |
| Exact search exceeds the time limit on an adversarial 24-card request | Low | Two bounds, stress test at 24 cards (step 5.2), deadline with a legal incumbent as fallback |
| A source edit after the recorded run makes results stale | Medium | Phase 9 runs after the review; Phase 11 fails if any `.py` hash differs from `python_sources_after` |
| Parallel phases drift from the fixed interfaces | Medium | Signatures are verbatim in the details file; Phase 8 integrates and its full gate is the check |
| Deadline overrun | Medium | Cut order: tune_search reference runs shortened, mid-range exact pass, consistency test on permuted copy, certificate. Never cut: validation, legality, recorded run, README |
| Solver wall time is higher on the grader's hardware than on this arm64 host | Medium | Deadlines are measured from process start with over 2 s of margin to the 5 s limit; disclosed in the README |

## Testing Approach

Unit tests per module; an independent checker and brute-force oracle that share no code with the solver; generated requests covering every constraint type and equivalence permutations; a corpus regression that runs all 28 public requests through the real CLI and checks each response with the independent checker; a trial container run before the recorded one; a post-run integrity and legality check over the recorder's actual output. Every gate runs as `<cmd> > gate.log 2>&1; echo rc=$?` and the exit code is read.

## Validation response (2026-10-11 12:53 PDT)

`hve-plan-validator` returned Fail with 0 Critical and 6 Major (planning log DR-004..DR-009, DD-008..DD-014). Each Major is resolved in this plan or the details file:

- DD-008 per-phase gate form: probe run in a scratch directory with `rootmod.py`, `tests/helper.py`, `tests/test_probe.py`. `python3.11 -m unittest tests/test_probe.py > gate.log 2>&1; echo rc=$?` gave `rc=1` (`FAILED (errors=1)`); `python3.11 -m unittest discover -s tests -p 'test_probe.py' > gate.log 2>&1; echo rc=$?` gave `rc=0` (`Ran 1 test ... OK`). Every per-phase gate now uses the `discover -s tests -p` form.
- DD-010 mid-range exact pass had no time: details section 8 now gives `solve_large` a 1.0 s deadline when `25 <= n <= 64` and `solve_exact` the remainder to 2.5 s; `solve_profile` gets the 2.5 s deadline.
- DD-009 undeclared dependencies: Phase 4 now depends on Phase 3 and moves to the second wave; Phase 8 depends on Phase 4; Phase 10 depends on Phase 4.
- DR-004 `check_results.py` now asserts per record: `exit_code == 0`, `timed_out` false, `response_parse_error` null, stdout is exactly one JSON object and one newline, `wall_ms < 5000`, `peak_rss_kib < 262144` (details section 9).
- DR-005 randomized differential test of ok versus infeasible: step 8.4a.
- DR-006 contract maxima end to end: step 8.4b; `gen.py` gains `max_request` (details section 4).

Minor items taken: bound wording tightened and moves restricted to usable cards (details sections 5 and 6); `build/` ignored via `.gitignore`, owned by Phase 4; instance count corrected to 18; search-deadline wording made consistent; response when `build_problem` itself crashes stated (details section 8); long exact runs on the three mid instances as 99% evidence (step 8.7). Not taken: a relaxation upper bound per large coupled instance (DR-007 second half), for time; named tests for R-05, R-15, R-21, R-34, R-42 reverse, R-75, R-85, A-14 are folded into steps 1.2 and 8.2 at the implementor's discretion (DR-008, Minor). A-15, A-18 and A-19 need no code: lone surrogates in `text` are accepted and never echoed, determinism is not required, and `mandatory` has no separate size limit (theme A artifact).

## Requirements added after plan approval

### 2026-10-11 12:57 PDT — implementation lands through reviewable pull requests (owner)

Owner's words: "Let's make sure to breakup chunks of implementation into reviewable pieces so that I can have Codex review, ideally as work broken up into appropriate PRs that can be merged into main after Codex's review and any re-work is done from the review".

This supersedes the kick-off's "Solo repo, no pull requests ... you integrate to main and push at each phase boundary". How every later phase command applies it:

- One pull request per plan phase, base `main`, branch `phase-N-<slug>`, body with a TL;DR, the files the phase owns, its gate command and result, and `Refs #<issue>` (no closing keywords). Milestone `director-context-picker`.
- Implementation never goes to `main` directly. The owner merges each PR after Codex's review and any rework. The orchestrator does not merge PRs and does not run Codex; it triages review findings and dispatches rework onto the phase branch.
- So that later phases are not blocked on review, phase branches are also merged into a local-and-pushed branch `integration` (main plus every delivered phase branch). A phase with dependencies starts from `main` plus `git merge integration`; its PR shows dependency files until those PRs merge, and its body lists the owned files to review. After a dependency PR merges, `main` is merged into the dependent branches.
- Tracking artifacts under `.claude-hve-tracking/` and repo hygiene (`.gitignore`) are not implementation and continue to be committed to `main` directly.
- Review rework and the recorded run: a `.py` change after the recorded run forces a rerun (Phase 9). Codex findings that arrive before the recorded run starts are reworked first. Findings that arrive later are reworked only if a rerun still fits before the deadline; otherwise they are listed as unfixed in the final report. The ZIP is built from `integration` (identical to `main` once every phase PR is merged); the final report states which PRs were merged at build time.
- Board: a phase issue moves to In review when its PR opens and is closed by gh-tracker when its phase is Complete and its PR is merged; if the PR is still open at the end, the issue stays In review with a comment saying why.

### 2026-10-11 13:00 PDT — reference scenarios as a second oracle (orchestrator decision, from an owner-side file)

`docs/reference-scenarios/` (README.md, build_scenarios.py, scenarios.json; 102 scenarios with brute-force expected answers) appeared untracked in the working tree at 12:48 PDT, written by the owner's other session, not by this workflow. It is used as an independent second oracle:

- Phase 8 adds `tests/data/reference_scenarios.json` (a byte copy of `docs/reference-scenarios/scenarios.json`) and `tests/test_reference_scenarios.py`: every scenario goes through the CLI (`raw_stdin` verbatim when present, else `request` serialized), exit code 0, `expect.status` matches, and for `ok` the utility equals `expect.utility` and the response passes `tests/checker.py`.
- Cross-check already run by the orchestrator at 12:59 PDT on `integration` (`5351980`): all 102 scenarios agree with `dcp_validate` (valid versus invalid), `dcp_model` (ok versus infeasible, active set), `tests/checker.py` (feasibility, active set) and `tests/oracle.py` (utility); 400 generated requests (130 infeasible) show 0 disagreements between the model and the checker and oracle. Command: an inline `python3.11` script in the integration worktree; output `reference scenarios: 102 | disagreements: 0` and `random differential: 400 requests, 130 infeasible, 0 disagreements`.
- The `docs/reference-scenarios/` folder itself is left untracked for its author to commit.
