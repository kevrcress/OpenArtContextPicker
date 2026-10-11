# Changes Log: Director context picker (`director-context.zip`)
Date: 2026-10-11
Plan: .claude-hve-tracking/plans/2026-10-11/director-context-picker-plan.md
Details: .claude-hve-tracking/details/2026-10-11/director-context-picker-details.md
Status: In Progress
Mode: full (`--mode full`): independent phases dispatched in parallel, each `hve-phase-implementor` in its own git worktree; the parent commits each worktree with its issue reference and merges to main. Each implementor edits only its own `### Phase N:` section of this file, in the main checkout, by absolute path.
Instructions: `~/.claude/instructions/python.md` and `python-tests.md` (global install; no project copy). Where they assume third-party tools (pytest, ruff, uv), the contract's standard-library-only rule wins: tests use `unittest`.

## Test Baseline
Tests: N/A — no test runner or test file exists in the repo before Phase 1 (0 passed, 0 failed, nothing pre-failing). Runner once tests exist: `python3.11 -m unittest discover -s tests -v`.

## Phases

### Phase 1: Strict input validation
Status: Complete
Started: 2026-10-11T19:53:23Z
Completed: 2026-10-11T19:57:51Z

Uncommitted in worktree `.claude/worktrees/agent-a947c80b3307c0474` (branch `worktree-agent-a947c80b3307c0474`); the parent commits and merges.

#### Files Modified
- `dcp_validate.py:1` — new, 296 lines. `MAX_BYTES` (`dcp_validate.py:12`), `InvalidRequest` (`dcp_validate.py:37`), `validate_request(raw: bytes) -> dict` (`dcp_validate.py:271`). Standard library only (`json`, `re`); imports no other `dcp_*` module.
- `tests/test_validate.py:1` — new, 722 lines, 86 `unittest` test methods in 9 classes. No `__init__.py` created.
- `.claude-hve-tracking/changes/2026-10-11/director-context-picker-changes.md:14` — this section, written in the WORKTREE copy (see Issues Encountered).

#### Steps Completed
- [x] Step 1.1: `InvalidRequest` and `validate_request` per details section 2 — `dcp_validate.py:37`, `dcp_validate.py:271`. Size check before decode (`dcp_validate.py:108`), strict UTF-8 decode, BOM rejection, `raw_decode` from the first non-whitespace index with a JSON-whitespace-only tail check (`dcp_validate.py:107`); decoder hooks for duplicate keys, float notation and non-finite constants (`dcp_validate.py:62`); version graph by Kahn's algorithm with strict-ancestor bitmasks (`dcp_validate.py:126`); features, cards (two passes so forward card references work), supersession ancestry (`dcp_validate.py:189`); contradictions with unordered-pair dedup (`dcp_validate.py:235`); catch-all conversion to `InvalidRequest` (`dcp_validate.py:295`).
- [x] Step 1.2: tests for every rule listed in the plan step, accepting and rejecting — `tests/test_validate.py:1`. The step 1.1 parser assumption [MEDIUM] is pinned by `test_json_decoder_python_defaults_pinned` and now holds as [HIGH] on the host's `python3.11`: `parse_float` receives `1.0` and `1e2`, `parse_constant` receives `NaN`/`Infinity`/`-Infinity`, default `json.loads` keeps the last duplicate key, a 5,000-digit literal raises `ValueError`, 100,000-deep nesting raises `RecursionError`.
- [x] Step 1.3: gate run as `python3.11 -m unittest discover -s tests -p 'test_validate.py' -v > gate.log 2>&1; echo rc=$?` — final run `rc=0`.

#### Issues Encountered
- Changes-log location: the brief said to edit this section in the MAIN checkout by absolute path. The Edit tool refused that path ("This agent is isolated in the worktree ... Edit the worktree copy of this file instead of the shared-checkout path"). I did not work around the guard through the shell. This section therefore exists only in the worktree copy, uncommitted; the main checkout's Phase 1 section still reads `Status: Pending` until the parent carries this section over.
- First gate run: `rc=1`, 86 run, 3 errors. All three were bugs in my own test fixtures, not validator behavior, and no rule expectation was changed: (1) the "good identifier" list used card id `a`, which collides with the base fixture's card `a` (correctly rejected as a duplicate id) — changed to `Z`; (2) and (3) `big_request()` made card `i` supersede card `i - 96`, which sits in the same version (correctly rejected) — changed to card `i - 1` for `i % 96 != 0`, a strict ancestor in the version chain. Second run `rc=0`.
- The details file and the contract did not disagree on any rule I implemented; no DR- entry.
- No instructions-file gap: `~/.claude/instructions/python.md` and `python-tests.md` were read; their third-party parts (`uv`, `ruff`, `pytest`, 3.12 target) were not applied, per the phase brief (Python 3.11 standard library only, `unittest`). Line length 120 kept (0 lines over).
- Sample-session test looks for `./director_session.json` then `./resources/director_session.json` and SKIPS if neither exists (the details file does not say fail-or-skip for this file, unlike the corpus). In this tree it ran; 0 skipped.

#### Discrepancies & Decisions
- DD-P1-01 (2026-10-11): `validate_request` passes a `parse_int` hook that rejects integer literals longer than 32 characters before conversion (`dcp_validate.py:49`). Details section 2 relies on the 3.11 default (`ValueError` over 4,300 digits). The accept/reject outcome is identical for every input, because every integer the contract allows is at most 4 digits and an integer anywhere else is a type error; the hook only removes the dependence on the interpreter's `int_max_str_digits` setting. Not a contract change.
- DD-P1-02 (2026-10-11): input whose first non-whitespace character is not `{` is rejected before JSON parsing (`dcp_validate.py:116`). Same outcome as parsing first (a non-object is invalid either way), without parsing a large non-object document.

#### Measurements (host `python3.11`, not the recorded Docker run)
- Corpus one-liner over `resources/benchmark_inputs.json` (28 instances, each `request` re-serialized with `json.dumps`): 26 validate, 2 raise `InvalidRequest` (the two reasons printed were "contradiction pairs a card with itself" and "contradiction must be an array of two card ids"). Whether those 2 are the corpus's intended `invalid` cases was NOT checked against expected statuses here (Phase 8 `tests/test_corpus.py` owns that).
- Slowest corpus validation: 9.22 ms, single run, for a 477,307-byte request with 488 cards and 6,496 pairs. The brief's 488-card, 7,424-pair instance was not identified separately in this pass; no instance took longer than 9.22 ms.
- Limit-sized generated request (96 versions, 500 cards, 1,024 features, 10,000 pairs, over 400,000 bytes) and the sample session each validate in under 100 ms (asserted by the two timing tests, best of 5).

Tests: 86 passed, 0 failed (0 skipped) — `python3.11 -m unittest discover -s tests -p 'test_validate.py' -v > gate.log 2>&1; echo rc=$?` gave `rc=0`, "Ran 86 tests in 0.178s", "OK".

---

<!-- end of phase 1 section; do not edit below this line from phase 1 -->


### Phase 2: Model and legality core
Status: Complete
Started: 2026-10-11T19:53:23Z
Completed: 2026-10-11T19:56:31Z

Work was done in the worktree `.claude/worktrees/agent-ad673c08bd763aad8` and left uncommitted there (untracked: `dcp_model.py`, `tests/test_model.py`; modified: this changes log, Phase 2 section only). Line numbers below are from that worktree copy.

#### Files Modified
- `dcp_model.py:13` — `Infeasible` exception (new file, 367 lines, standard library only)
- `dcp_model.py:18` — frozen `Problem` dataclass, the 15 fields of details section 3 in the given order, none added
- `dcp_model.py:38` — `_visible_versions`: head plus ancestors, explicit stack
- `dcp_model.py:51` — `_active_ids`: visible cards not reachable through `supersedes` from a visible card, explicit stack
- `dcp_model.py:72` — `_closures`: iterative Tarjan over the `requires` graph of all cards; a component is dead (closure 0) when it contains or reaches a non-active card; cover and conflict are OR-propagated per component
- `dcp_model.py:180` — `build_problem`: masks, group and pair conflicts, closure tokens, dependents, mandatory feasibility, usable set
- `dcp_model.py:305` — `mask_tokens`, `mask_cover` (310), `cover_weight` (321), `is_legal` (326), `mask_ids` (348), `fmask_ids` (359)
- `tests/test_model.py:1` — 55 unittest cases in 8 classes (new file, 531 lines)

#### Steps Completed
- [x] Step 2.1: `Infeasible`, `Problem`, `build_problem` and the mask helpers per details section 3 — `dcp_model.py:13`, `dcp_model.py:18`, `dcp_model.py:180`, `dcp_model.py:305`
- [x] Step 2.2: Tests for every case the step lists — `tests/test_model.py:1`. Merge head and invisible branch (`TestVisibility`); chain, superseded superseder, invisible superseder (`TestSupersession`); requires on inactive or invisible card, cycle, self-requirement, shared requirement charged once, 500-deep chain (`TestClosures`); pair or same group inside a closure, inert pair with inactive endpoint, no transfer to a successor, non-transitivity (`TestConflicts`); mandatory inactive, invisible, pair in closure, same group, over budget, exact budget, empty mandatory at budget 0 (`TestMandatory`); one rejection per contract condition 1 to 6 (`TestIsLegal`); sample session numbers (`TestSampleSession`)
- [x] Step 2.3: Timing on `resources/benchmark_inputs.json` instance `i_3b971612ce637e324b` (488 cards, 7,424 pairs, 476 active, 475 usable): `build_problem` min 3.05 ms, median 3.25 ms, max 5.08 ms over 25 in-process runs on the host with `python3.11` and `time.perf_counter`. Target was under 60 ms. Worst single first-call build over all 28 public instances: 3.78 ms. The corpus was read only, loaded inside a `python3.11 -c` one-liner
- [x] Step 2.4: Gate `python3.11 -m unittest discover -s tests -p 'test_model.py' -v > gate.log 2>&1; echo rc=$?` printed `rc=0`; `gate.log` reads `Ran 55 tests in 0.031s` and `OK`

#### Sample session facts pinned in tests
`n == 7`, ids `amber_arrival, closeup, coat, moon, neon, portrait, sleeve_detail` (no `jacket`); closures portrait 32, coat 55, neon 20, moon 18, closeup 47, sleeve_detail 44, amber_arrival 102; mandatory closure `{portrait}`; usable `{closeup, coat, moon, neon, sleeve_detail}` (amber_arrival active, not usable); exhaustive `is_legal` scan over 128 masks gives best utility 61, reached by portrait + sleeve_detail + closeup with either moon or neon.

#### Issues Encountered
- Changes-log location: the brief said to edit the MAIN checkout copy of this file by absolute path. The Edit tool refused that path ("This agent is isolated in the worktree ... Edit the worktree copy of this file instead"). The section was written to the worktree copy instead, so the parent has to carry this section into the main checkout when it merges. The guard was not worked around through the shell.
- No instructions-file gap: `~/.claude/instructions/python.md` and `python-tests.md` were read. Their third-party parts (uv, ruff, pytest, `tmp_path`, parametrize) do not apply here by brief: tests use `unittest`, test methods keep the `test_{function}_{scenario}_{outcome}` naming.
- One public instance, `i_57be790be38419e246`, makes `build_problem` raise `ValueError` ("too many values to unpack (expected 2)", from unpacking a contradiction entry). It is a request the Phase 1 validator must reject before `build_problem` is called; `build_problem` assumes validated input by design and does not guard against it. Phase 8 must keep validation ahead of `build_problem`. [HIGH for the raise, observed; MEDIUM that the request is one the validator rejects, inferred from the error text only, the instance was not inspected]
- 2 of the 28 public instances raise `Infeasible` from `build_problem`; not investigated further here, out of scope for this phase.
- Extra check, not a unit test: on the 25 public instances that build, all 6,153 active-card closures and closure token sums match a naive per-card walk, and `is_legal(p, p.mandatory)` holds (0 mismatches).
- No timing assertion was put in the test file (a wall-clock assert would be flaky); the number above is the record for step 2.3.

#### Discrepancies & Decisions
- DD-P2-1 (2026-10-11): `dependents[i]` always has bit `i` set, including for a card whose `closure[i] == 0`. Details section 3 defines it as "active cards j with closure[j] containing i (includes i)"; for a closure-0 card the two halves of that sentence disagree. Chose the literal "(includes i)" so the invariant holds for every card. No other card can appear in the dependents of a closure-0 card, since a card requiring it also has closure 0. Consumers only ever remove selected cards, which have nonzero closures, so behavior is unaffected.
- DD-P2-2 (2026-10-11): `is_legal` returns False for a negative mask or a mask with a bit at or above `n`. Contract condition 1 (selected cards are active and visible) is otherwise carried by the representation: only active cards have bits. A card that requires an inactive card is rejected through `closure[i] == 0`.
- DD-P2-3 (2026-10-11): `Infeasible` reasons are fixed ASCII strings and never include request ids, matching the validator's rule of not echoing request text.
- No DR- items: the details file and contract lines 64-101 agree on everything implemented.

Tests: 55 passed, 0 failed (`python3.11 -m unittest discover -s tests -p 'test_model.py' -v`, rc=0)

---

<!-- end of phase 2 section; do not edit below this line from phase 2 -->


### Phase 3: Independent legality checker, oracle and generators
Status: Complete
Started: 2026-10-11T19:53:24Z
Completed: 2026-10-11T19:58:12Z

Work was done in worktree `.claude/worktrees/agent-a36fe6f91b2ba87e3` (branch `worktree-agent-a36fe6f91b2ba87e3`), left uncommitted for the parent to commit and merge.

#### Files Modified
- `tests/checker.py:1` — new, 280 lines. `visible_versions` (`:23`), `active_cards` (`:36`), `requires_closure` (`:55`), `legality_errors` (`:69`, the six conditions, messages prefixed `condition N:`), `expected_feasible` (`:103`), `response_for` (`:109`), `certificate_errors` (`:146`, messages prefixed `certificate:`), `check_response` (`:178`), `certificate_bound` (`:247`), `is_certificate_profile` (`:264`). Sets and dicts on the raw request; explicit stacks, no recursion.
- `tests/oracle.py:1` — new, 100 lines. `best_set` (`:13`) and `best_utility` (`:95`). Explicit-stack include/exclude enumeration over active cards with its own closure, group, pair, budget and mandatory tests; takes only the active set from `checker`.
- `tests/gen.py:1` — new, 224 lines. `random_request` (`:53`), `max_request` (`:110`), `permute_request` (`:182`).
- `tests/test_checker_oracle.py:1` — new, 560 lines, 45 `unittest` tests, including its own structural input-contract validator `assert_valid_request` so the generators are not their own judge.

#### Steps Completed
- [x] Step 3.1: `checker.py` per details section 4, written from the contract text (lines 80-145), with sets and dicts — `tests/checker.py:1`
- [x] Step 3.2: `oracle.py` exhaustive search over subsets of active cards — `tests/oracle.py:13`
- [x] Step 3.3: `gen.py` `random_request`, `permute_request` and `max_request` — `tests/gen.py:53`
- [x] Step 3.4: Self-tests pinned to hand-derived values (sample session 7 active and optimum 61; the seven tiny public requests; one illegal response per legal-set condition; certificate formula by hand) and `permute_request` preserving `best_utility` on 30 generated requests — `tests/test_checker_oracle.py:176`
- [x] Step 3.5: Gate run: `python3.11 -m unittest discover -s tests -p 'test_checker_oracle.py' -v > gate.log 2>&1; echo rc=$?` gave `rc=0`

#### Issues Encountered
- This section was written to the WORKTREE copy of the changes log, not the main checkout as the brief asked: the Edit tool refused the main-checkout path ("This agent is isolated in the worktree ... Edit the worktree copy of this file instead"). The refusal was not worked around. The parent has to carry this section into the main-checkout log (it is an uncommitted change to this one file, confined to the Phase 3 section).
- First gate run: rc=1, 1 error in 45 tests. Cause was in the test file only: a helper named `_outcome` shadowed `unittest.TestCase._outcome`. Renamed to `_solve`; second run rc=0. No expectation was changed.
- `~/.claude/instructions/python.md` and `python-tests.md` assume pytest, ruff, uv and Python 3.12+. Per the phase brief those parts were not applied (Python 3.11 standard library, `unittest`). Applied: type hints on public functions, `from __future__ import annotations`, f-strings, 120-column lines, seeded randomness only. Only the first ~2.5 KB of each instructions file was read (time limit).
- Success criterion `grep -n "import dcp" tests/checker.py tests/oracle.py tests/gen.py`: no output (grep exit 1). The same check is also a test (`IndependenceTests`).
- Oracle timing measured on the host: 18 active cards 0.20 s, 20 active cards 0.79 s (a request where no pruning is possible).
- Not run: ruff or any linter (none is a project dependency). Not run: the full `discover -s tests` suite (other phases' files are not in this worktree).
- `git status --short -uall` after the gate lists only the four owned files plus this log: `gate.log` and `tests/__pycache__/` are ignored.

#### Discrepancies & Decisions
- DD-P3-1 (2026-10-11): `check_response(request, response, *, request_valid: bool = True)` adds a keyword-only argument to the signature in details section 4. Reason: the parent brief asked for it so the two invalid tiny requests (i_93a2, i_57be) can be pinned. With `request_valid=False` the only accepted response is exactly `{"status": "invalid", "reason": <nonempty str>}`. Callers written against details section 4 are unaffected.
- DD-P3-2 (2026-10-11): Added helpers beyond details section 4, all additive: `checker.visible_versions`, `checker.requires_closure`, `checker.legality_errors`, `checker.response_for(request, selected)` (an `ok` response with honestly recomputed totals, no legality check), `checker.certificate_errors`, and `oracle.best_set(request, limit=20) -> (utility, sorted ids)`. `best_utility` wraps `best_set`.
- DD-P3-3 (2026-10-11): A malformed or out-of-range certificate on an otherwise correct `ok` response IS reported by `check_response`, with every such message prefixed `certificate:`. The contract (line 145) judges certificates apart from the core fields, so a caller grading the core only must filter that prefix. Certificate tightness (`100 * U <= 105 * utility * s`) is NOT checked by `check_response`; callers compute it from `certificate_bound`.
- DD-P3-4 (2026-10-11): `oracle` is not fully independent of `checker`: it calls `checker.active_cards` (allowed by the brief). Its legality test is its own code. A bug in visibility or supersession would therefore be shared between the two; that part is pinned by hand-derived tests (`SupersessionTests`, tiny i_f4bb, sample session 7 active).
- DD-P3-5 (2026-10-11): `gen.max_request` sets `mandatory: []`, so it is always feasible. In the non-profile form the 200-card requires chain is `c0 -> c1 -> ... -> c199`, the cycle is `c200 -> c201 -> c202 -> c200`, and groups `g0..g19` are only on cards `c203` and above. `gen.random_request` draws feature weights from 1-100, not 1-1,000.

Tests: 45 passed, 0 failed (`Ran 45 tests in 0.413s`, `OK`, rc=0)

---

<!-- end of phase 3 section; do not edit below this line from phase 3 -->


### Phase 4: Packaging and Docker benchmark harness
Status: Complete
Started: 2026-10-11T20:02:18Z
Completed: 2026-10-11T20:07:41Z

#### Files Modified
- `tools/build_package.py:1` — new (137 lines). `build(source, out, verify=False)`, `check_resources`, `planned_files`, `verify_results`; CLI `--out`, `--source` (default parent of `tools/`), `--verify-results`. Baseline hashes at `tools/build_package.py:21`.
- `tools/run_recorded.sh:1` — new (65 lines, executable). Docker recorder run with `--cpus=2 --network none`, no memory cap, relative paths inside the container.
- `tools/check_results.py:1` — new (261 lines). `evaluate(results, corpus, checker, ...)`, `render(summary)`, `stdout_is_one_object`, `nearest_rank_p95`, `load_checker` (loads `tests/checker.py` by path); CLI `<dir>`, `--json PATH`, `--allow-wrong`. Baseline hashes at `tools/check_results.py:22`.
- `tools/make_zip.py:1` — new (64 lines). Sorted entries at the archive root, timestamp 1980-01-01, deflate level 9, mode 0644 or 0755.
- `tests/test_tools.py:1` — new (280 lines, 18 tests). Loads the three Python tools by path; all file work in `tempfile` directories.
- `.gitignore` — NOT edited (parent instruction: `build/` and `.claude/worktrees/` are already ignored on main; this supersedes the plan's "Add `build/` to `.gitignore`").

#### Steps Completed
- [x] Step 4.1: `build_package.py`, `run_recorded.sh`, `make_zip.py`, `check_results.py` — `tools/build_package.py:95`, `tools/run_recorded.sh:19`, `tools/make_zip.py:33`, `tools/check_results.py:94`. The `.gitignore` part of this step was withdrawn by the parent (see Files Modified).
- [x] Step 4.2: `tests/test_tools.py` — byte-identical recorder and corpus copy (`tests/test_tools.py:75`), refusal on a hash mismatch simulated on a temp copy of `resources/` (`tests/test_tools.py:89`), zip entries at the archive root without `__pycache__` or `.DS_Store` (`tests/test_tools.py:152`); also `--verify-results`, deterministic zip bytes, and `check_results.evaluate` on two real corpus requests.
- [x] Step 4.3: Stub dry run under Docker in a scratch directory outside the repo (commands and output below).
- [x] Step 4.4: `resources/` hashes equal the baseline after the dry run (output below).

Step 4.3 commands, run from the worktree root with `S=/var/folders/t2/lgmxzs012z19716my6ky1hdh0000gn/T/tmp.k3BTMLT6xe` (from `mktemp -d`). `$S/src` held copies of `tests/`, `tools/`, `dcp_model.py`, `dcp_validate.py`, the three supplied files under `resources/`, and a three-line stub `context_solver.py` that reads stdin and prints `{"status":"invalid","reason":"stub"}`:

```
$ python3.11 tools/build_package.py --source $S/src --out $S/pkg; echo "build rc=$?"
build_package: warning: no README.md in the source tree
packaged 17 files into /private/var/folders/t2/lgmxzs012z19716my6ky1hdh0000gn/T/tmp.k3BTMLT6xe/pkg
build rc=0
$ tools/run_recorded.sh $S/pkg; echo "run rc=$?"
rc=0
run rc=0
$ wc -l $S/pkg/benchmark_run.log
      28 .../pkg/benchmark_run.log
$ python3.11 tools/check_results.py $S/pkg --json $S/summary.json > $S/check.out 2>&1; echo "check rc=$?"
check rc=1
```

Key lines of `$S/check.out`:

```
- ok: runner_sha256 (87694477eca9636ed78766d4473821befb9d388bf2444b2e1b5310f5e6ca5943)
- ok: inputs_sha256 (164ea460ed919a4e5e365c5357b9d53606f8f5fb53df8c238664c8117eae541c)
- ok: python_sources_unchanged (True)
- ok: quota_vcpus == 2.0 (2.0)
- ok: 28 records (28)
- ok: record ids match the corpus in order (28 records, 28 corpus instances)
- ok: benchmark_inputs.json on disk matches the baseline (164ea4...541c)
| i_353b0868e8bfb0bb1c | 3 | invalid | - | - | 123 | 16252 | False | FAIL |
| i_d377627acc7b53786a | 476 | invalid | - | - | 21 | 16844 | False | FAIL |
- status counts: invalid=28
- max wall_ms overall: 354.07258400000075
- valid feasible requests with at least 250 active cards: n=15, p95 wall_ms (nearest rank)=291.797791999997, max peak_rss_kib=16844
- certificates: none present on a profile instance
- consistency i_d377627acc7b53786a / i_b05b69c48293a3d4b4: L=-, H=-, 200*(H-L) <= H: -
    "cgroup_cpu_max": "200000 100000",
    "quota_vcpus": 2.0
  "invocation": "benchmark_runner.py --solution context_solver.py --inputs benchmark_inputs.json --output benchmark_results.json",
  "python": "3.11.17 (main, Oct  6 2026, 02:08:45) [GCC 14.2.0]",
RESULT: FAIL (26 of 28 records failed, 0 integrity checks failed)
```

Table verdict counts: 2 `pass` (the two known-invalid requests, where the stub's `invalid` is the right answer), 26 `FAIL`. No `__pycache__` was left in `$S/pkg` after the run. The stub timings above are recorder overhead only and are not solver measurements.

Round trip of the recorded results (same scratch tree, after `cp $S/pkg/benchmark_results.json $S/src/`):

```
$ python3.11 tools/build_package.py --source $S/src --out $S/pkg3 --verify-results; echo "verify rc=$?"
packaged 18 files into .../pkg3
verify rc=0
$ python3.11 tools/make_zip.py $S/pkg3 $S/dc.zip
.../dc.zip: 18 entries, 974459 bytes
```

Step 4.4:

```
$ shasum -a 256 resources/benchmark_runner.py resources/benchmark_inputs.json
87694477eca9636ed78766d4473821befb9d388bf2444b2e1b5310f5e6ca5943  resources/benchmark_runner.py
164ea460ed919a4e5e365c5357b9d53606f8f5fb53df8c238664c8117eae541c  resources/benchmark_inputs.json
```

#### Issues Encountered
- The first `tools/run_recorded.sh` call failed before the container started: `docker: request returned 500 Internal Server Error for API route ... /containers/create` (exit 125, no results file, nothing written). Two plain `docker run` probes right after succeeded and the unchanged script then ran to `rc=0`. Cause not established [LOW: Docker Desktop load from parallel agents]. The script has no retry; a repeat in Phase 9 needs a re-run by hand in a fresh directory.
- No `.claude/instructions/` directory in the project; the global `~/.claude/instructions/python.md` and `bash.md` were used. `python.md` targets 3.12+ with `uv` and `ruff`; the plan binds Python 3.11 standard library, so neither tool was run. `shellcheck` was not run on `run_recorded.sh`.
- `python-tests.md` was not read (time limit), and no existing test file was read for style; the tests are plain `unittest.TestCase` classes as details section 1 requires.
- The gate's `gate.log` interleaves the tools' own stdout lines with the unittest report; counts were read from the `Ran`/`OK` lines.

#### Discrepancies & Decisions
- DD-P4-01 (2026-10-11): the two contract-breaking public requests are identified by id (`KNOWN_INVALID_IDS`, `tools/check_results.py:30`) and not by re-validating, so the script never imports the solver. A corpus with other invalid requests would be judged as valid; the script is for the public corpus only.
- DD-P4-02 (2026-10-11): the certificate gap (`100*U <= 105*utility*s`) and the pair consistency ratio (`200*(H-L) <= H`) are printed and written to the JSON summary but do not change the exit code; details section 9 lists them under "prints", not "asserts". Certificate shape errors from the checker (`certificate:` prefix) DO fail the record.
- DD-P4-03 (2026-10-11): beyond details section 9, `check_results.py` also asserts that record ids equal the corpus ids in order, that each `input_sha256` equals the canonical hash of the corpus request, and that the `benchmark_inputs.json` on disk matches the baseline.
- DD-P4-04 (2026-10-11): `run_recorded.sh` refuses to run when `benchmark_results.json` already exists in the directory (a stale file would hide a failed run) and never deletes it. `build_package.py` refuses a non-empty `--out` and a source without `context_solver.py`; a missing `README.md` is a warning only.
- DD-P4-05 (2026-10-11): `--allow-wrong` is implemented as asked (report printed, exit 0, a notice on stderr). It was not used in the dry run.

Tests: 18 passed, 0 failed (`python3.11 -m unittest discover -s tests -p 'test_tools.py' -v > gate.log 2>&1; echo rc=$?` gave `rc=0`; `gate.log` reads `Ran 18 tests in 0.493s` and `OK`)

---

<!-- end of phase 4 section; do not edit below this line from phase 4 -->


### Phase 5: Exact search for 24 or fewer active cards
Status: Complete
Started: 2026-10-11T20:02:18Z
Completed: 2026-10-11T20:09:32Z

#### Files Modified
- `dcp_exact.py:1` — new, 234 lines. `solve_exact(p, deadline, incumbent=None) -> (mask, proven)` at `dcp_exact.py:63`; closure-aware greedy seed `_greedy` at `dcp_exact.py:27`. Explicit stack, no recursion.
- `tests/test_exact.py:1` — new, 314 lines, 11 tests: oracle agreement, 24-card stress over 16 instance families, deadline, incumbent and deep-chain behaviour.

#### Steps Completed
- [x] Step 5.1: Implement `solve_exact` per details section 5 — `dcp_exact.py:63`
- [x] Step 5.2: Oracle comparison tests and the 24-card stress test — `tests/test_exact.py:171` (oracle), `tests/test_exact.py:230` (stress)
- [x] Step 5.3: Run the gate for `tests/test_exact.py` — rc=0

#### Issues Encountered
- The plan's `[MEDIUM]` assumption (the two bounds finish 24-card worst cases under 1.5 s) held for the three families the plan names from the first version (worst 0.003 s), but NOT for a family the plan does not name. A probe outside the gate found budgeted maximum coverage with wide, lightly overlapping covers (24 equal-token cards, 1,000 features, 40 to 64 covers each, budget 40% of the token sum) taking 11.4 s, and sparse-conflict independent set (private near-equal features, no budget pressure) taking 0.7 s. Per the step 5.2 guard the search was strengthened before closing: marginal gains are now carried down the stack and adjusted only by the newly covered features, the knapsack bound runs before the union bound, and the union bound uses byte tables. Same probe after the change: 0.31 to 0.96 s for the coverage family across three seeds, 0.01 to 0.2 s for the independent-set family.
- Residual risk [MEDIUM]: the coverage family is the worst found and has little margin. Measured worst case at 24 active cards: **1.065 s**, family "24 equal-token cards, 1,024 features, 50 to 64 covers per card, budget 33% of the token sum" (probe script, 4 instances, host under load from parallel phases; the same family measured 1.374 s before the last change). Inside the gate the worst is 0.308 s (`k-cover-wide case 2`, 80 cases). Only 12 probe instances of the coverage variants were timed, so a hidden instance of this shape above 1.5 s on the recorded-run host cannot be ruled out. The solver stays exact whatever the time; the exposure is the caller's deadline, which Phase 8 owns.
- First deadline test failed (0.115 s against a 0.07 s limit at 500 usable cards) with the clock read every 32 nodes; fixed by DD-P5-2, then passed.
- `gate.log` is written in the worktree root by the gate and was not committed; `git status --short` does not list it (ignored).
- NOT RUN: the full `python3.11 -m unittest discover -s tests -v` suite (only this phase's file, per the phase rule); no timing inside Docker.

#### Discrepancies & Decisions
- DR-P5-1: wide maximum-coverage instances at 24 active cards are far harder for bounds (a) and (b) than the plan's three stress families (11.4 s before strengthening; evidence in Issues Encountered). The plan's stress list does not cover them; they were added to the gate as `k-cover-wide` and `k-cover-quarter`, with `independent-set-1` and `independent-set-2`.
- DD-P5-1 (2026-10-11): eligibility uses `closure_conflict[c] & S == 0` instead of the details' `conflict[c] & S == 0`. It is a subset of the details' eligible set and still contains every card a legal extension can add (a card's whole closure joins the set, so no closure member may conflict with S), so both bounds stay valid and get tighter.
- DD-P5-2 (2026-10-11): the clock is read once per about 4,096 card visits rather than every 256 nodes as details section 5 says. With 500 usable cards a node costs about 1 ms, so 256 nodes would overshoot the deadline by far more than 20 ms; the work counter keeps the overshoot near 1 ms at any size. At 24 cards this is a read every 100 nodes or so.
- DD-P5-3 (2026-10-11): bound (a) is evaluated on every node only while it prunes at least 1 in 16 of its tries; otherwise on one node in 16. Skipping a bound cannot lose optimality. Bound (b) and the plain gain-sum bound run on every node.
- DD-P5-4 (2026-10-11): the greedy seed is skipped when an incumbent is given and more than 64 cards are usable (its cost there is quadratic); the first dive of the search is itself a greedy by gain per token.
- DD-P5-5 (2026-10-11): features with weight 0 or less and features already covered by the mandatory set are masked out of the search; utility is counted relative to the mandatory set. Assumes feature weights are never negative [MEDIUM] (not checked against `dcp_validate` in this phase).
- Instructions files: `~/.claude/instructions/python.md` and `python-tests.md` were NOT read (time limit); the code follows the conventions of `dcp_model.py` and `tests/test_model.py` instead.

Tests: 11 passed, 0 failed — `python3.11 -m unittest discover -s tests -p 'test_exact.py' -v > gate.log 2>&1; echo rc=$?` gave `rc=0`, `Ran 11 tests in 10.149s`, `OK`.
- Oracle comparisons, all equal with `proven` true: at least 300 of 420 generated requests with 1 to 16 active cards (the test asserts the 300 floor; infeasible draws are checked for agreement, `Infeasible` against `LookupError`, and not counted), 128 family cases at 10 to 16 active cards (16 families x 8), 7 cases at 18 and 20, 2 hard-family cases at 20, the three public small instances (12, 16 and 18 active) and `resources/director_session.json`.
- 24 active cards: 80 cases (16 families x 5), each `proven` under 1.5 s; the 15 knapsack cases equal an independent dynamic programme; 32 cases re-solved on a renamed copy (`gen.permute_request`, different bit order) with equal utility. There is no oracle at 24 cards, so the non-knapsack 24-card cases have no independent optimum check beyond that.

---

<!-- end of phase 5 section; do not edit below this line from phase 5 -->


### Phase 6: Large-instance search
Status: Blocked — code and tests are complete and the gate passes, but the plan's quality criterion (2.0 s result at least 99% of the reference on every public large instance) is NOT met; see DR-601.
Started: 2026-10-11T20:02:19Z
Completed: 2026-10-11T20:12:33Z (last clock reading before this entry was written; work stopped at the 18-minute limit)

#### Files Modified
- `dcp_search.py:38` — `solve_large(p, deadline, seed=20261011, *, max_moves=0) -> int`; legal-mask fallback chain (best seen, greedy, `p.mandatory`), `is_legal` checked once at the end
- `dcp_search.py:55` — `_search`: bitmask state plus per-feature cover counts, running tokens and utility, add/drop journal for undo
- `dcp_search.py:136` — `refill(banned, mode)`: greedy fill, three rules (0 gain per marginal token, 1 gain, 2 gain per 1 + addable cards the unit would block)
- `dcp_search.py:187` — construction: the three greedy rules, best kept
- `dcp_search.py:219` — three-phase portfolio local search (ejection, sampled token shedding, refill, plateau acceptance, perturbation)
- `tests/test_search.py:1` — 10 tests (new file)
- `tools/tune_search.py:1` — tuning table (new file; `--quick`, `--jobs`)

#### Steps Completed
- [x] Step 6.1: Greedy construction and incremental cover counts — `dcp_search.py:136`, `dcp_search.py:187`
- [x] Step 6.2: Ejection-and-refill local search with perturbation, deadline handling and legal fallback — `dcp_search.py:219`, `dcp_search.py:38`
- [x] Step 6.3: `tests/test_search.py` and `tools/tune_search.py` — `tests/test_search.py:1`, `tools/tune_search.py:1`
- [ ] Step 6.4: tune table run and pasted below, but only with `--quick` (5 s references, not 20 s) and on a host at load average about 30 (other agents running); the 99% criterion fails on 3 of 18 by the table and on more in truth (DR-601)
- [x] Step 6.5: gate run, rc=0

#### Algorithm as built
- Construction from `p.mandatory` with three greedy rules; the best is the greedy result.
- Move: pick a random usable card c outside S; evict the selected cards in `closure_conflict[c]` plus their selected dependents (skip if that touches `p.mandatory`); add `closure[c]`; while over budget drop the unit with the least lost weight per freed token among 8 sampled selected cards; refill greedily; accept when utility does not decrease, else undo from the journal.
- Perturbation after `min(600, max(120, usable))` moves without a strict improvement: return to the phase best if behind, remove 2 to 5 random units, refill without them, refill again.
- Portfolio: 25% of the time from the per-token greedy with rule 0, 25% from the per-blocked-card greedy with rule 2, the remaining 50% from the best set seen with the rule that found it.
- Clock: checked every loop iteration, every refill pass, and before every multi-card closure evaluation.

#### Issues Encountered
- The host was heavily loaded during every measurement (`uptime` load average 30.55 on 8 cores at 20:07Z). Wall-time numbers are pessimistic and noisy. Moves per CPU-second (process time, before the portfolio change): 12,661 to 31,841 loop iterations on the 476-card instances, 20,000 to 45,000 on the 284 to 428-card ones, about 250,000 on the mid instances.
- No `.claude/instructions/python.md` deviation known; conventions followed from the existing modules.

#### Tune table (`python3.11 tools/tune_search.py --quick --jobs 6`, final code, 5 s references, loaded host)

```
reference: best of 3 runs of 5 s; jobs=6
id                      act unit  greedy    0.3s    1.0s    2.0s     ref 2.0s/ref  moves/s
i_6f0cb82b21cc17afba    380  yes     165     223     223     223     223   1.0000    17020
i_5fccaf00f31313dcfc    428  yes      66      69      71      72      72   1.0000    10752
i_613d784770e53c543d    428  yes     103     120     120     120     120   1.0000    12794
i_91a2e8f7679a6871f4    428  yes      66      70      70      71      73   0.9726     6934  BELOW 99%
i_3b971612ce637e324b    476  yes     128     128     128     128     128   1.0000    13510
i_d755f5d407b0d86c60    476  yes      64     136     136     136     136   1.0000    13878
i_9cf7bcb5fe8c0fdac3     36   no    5394    5471    5471    5471    5471   1.0000    97876
i_4f87def68141976d87     48   no    6484    6659    6659    6659    6659   1.0000   124561
i_3fa5a35f7c751fc671     64   no    8362    8606    8606    8606    8606   1.0000   124571
i_9e24f6f61fea4413ac    256   no   78170   78170   78170   78170   78170   1.0000   113886
i_a7373a7648d6ddce67    284   no   30761   40568   40568   40568   40568   1.0000    18953
i_cf46e9e6258788de2a    320   no   58666   58666   58666   58666   58666   1.0000    32072
i_27d35bf2cd22d3769a    332   no   34708   37007   49814   49814   37495   1.3286    20054
i_dfcebb3746dc9feecb    332   no   34708   36338   37942   37942   37678   1.0070    14331
i_97504cfbf824b0eeee    380   no   36090   37957   38356   40144   40477   0.9918     9860
i_8d29a9554dd222d976    476   no   42206   71309   71285   71215   71374   0.9978     3391
i_b05b69c48293a3d4b4    476   no   60354   61310   61477   61477   73602   0.8353     6549  BELOW 99%
i_d377627acc7b53786a    476   no   60354   61183   61165   61310   73602   0.8330     9282  BELOW 99%
worst 2.0s/ref ratio: 0.8330 (i_d377627acc7b53786a)
```

The six unit-weight instances are the first six rows. Below 99% of the reference: i_91a2e8f7679a6871f4 (71 of 73, unit weight), i_b05b69c48293a3d4b4 (61,477 of 73,602), i_d377627acc7b53786a (61,310 of 73,602). The 18 rows are every public instance with `p.n >= 25` that `build_problem` accepts (13 large, 3 mid, 2 others).

#### Discrepancies & Decisions
- DR-601 (Major, blocks the success criterion): the large public instances contain a far better solution that the search reaches only in some runs, so results are bimodal and the "reference" is not an upper bound. Evidence, all from this session: i_dfcebb3746dc9feecb returned 49,814 in one run and 37,079 in another; the two sets differ in 88 cards, the better one uses 1,367 of 1,433 tokens with 104 cards and the worse 933 tokens with 75 cards, and the better set's cards all have conflict degree 18 and closures of 2 to 4 cards. Same pattern: i_27d35bf2cd22d3769a 49,814 at 2.0 s but 37,495 in its own 5 s reference (ratio 1.33); i_613d784770e53c543d 120 after the third greedy rule against 73 before it; i_8d29a9554dd222d976 71,215 against 44,891 before; i_b05b69c48293a3d4b4 and i_d377627acc7b53786a 73,602 in a reference run against about 61,400 at 2.0 s. i_5fccaf00f31313dcfc and i_91a2e8f7679a6871f4 (same size and type as i_613d784770e53c543d, which reaches 120) stay at 71 to 73, so their references are probably far too low [MEDIUM]; i_97504cfbf824b0eeee likewise unverified [LOW]. Consequence: a 1.0000 ratio in the table does not show the hidden 99% bar is met, and the repeat pair i_27d35bf2cd22d3769a / i_dfcebb3746dc9feecb (49,814 against 37,942) would fail phase 8's consistency assertion `200*(H-L) <= H`. Not resolved in this phase.
- DR-602 (Minor): with the clock checked every 32 moves the function returned 58 to 172 ms late on closure-heavy inputs (gate failures on `gen.max_request` and two public instances, under load). One refill pass over a 200-card requires chain cannot be interrupted between cards.
- DD-601 (2026-10-11): resolves DR-602. The clock is read every loop iteration, every refill pass and before every multi-card closure evaluation (`CLOCK_EVERY = 1`). The brief's "at most every 32 moves" is read as an upper bound on the interval; a read costs about 40 ns against a move of 20 microseconds or more.
- DD-602 (2026-10-11): added a third greedy rule (gain per 1 + addable cards blocked) and a three-phase portfolio, in response to DR-601. Details section 6 names two greedy rules; this adds to them.
- DD-603 (2026-10-11): `solve_large` takes an extra keyword-only `max_moves=0` (0 means no limit) so variants can be compared by work done on a loaded host. The binding positional interface is unchanged. `dcp_search.LAST_STATS` (moves, perturbations, greedy utility and rule) is diagnostic only.
- DD-604 (2026-10-11): `tools/tune_search.py` runs instances in worker processes (`--jobs`, default 4) and adds greedy and moves-per-second columns; the brief specified the other columns.

#### Not run
- The 20 s reference table (only `--quick`).
- Any measurement on an idle host; the moves-per-second column is wall time under load.
- The "within 50 ms of the deadline" check on an idle host (it passes in the gate under load).

Tests: 10 passed, 0 failed (`python3.11 -m unittest discover -s tests -p 'test_search.py' -v > gate.log 2>&1; echo rc=$?` gave rc=0, "Ran 10 tests in 8.699s", OK; run on the final code)

---

<!-- end of phase 6 section; do not edit below this line from phase 6 -->


### Phase 7: Certificate-profile knapsack and certificate
Status: Complete
Started: 2026-10-11T20:02:19Z
Completed: 2026-10-11T20:04:53Z

Worked in worktree `agent-aeb0598f2739d1873` after `git merge --no-edit integration` (merge commit only; both phase files left uncommitted for the parent).

#### Files Modified
- `dcp_profile.py:19` — `profile_applies(req, p)`: no requires, no group on ANY card of the request, no pairs, active covers pairwise disjoint (checked on `p.cover`)
- `dcp_profile.py:39` — `solve_profile(p, deadline)`: exact 0/1 knapsack over `p.usable` with `p.mandatory` forced; one `bytes` decision row per item; `None` on deadline
- `dcp_profile.py:87` — `_bound`: the contract's `U` for `feature_prices[f] = weight * scale`
- `dcp_profile.py:98` — `build_certificate(p, mask)`: break-card candidates plus `(1, 0)`, exact integer comparison, returned only when `100*U <= 105*utility*scale`
- `tests/test_profile.py:1` — new, 22 tests in 4 classes

#### Steps Completed
- [x] Step 7.1: `profile_applies`, `solve_profile`, `build_certificate` per details section 7 — `dcp_profile.py:19`, `dcp_profile.py:39`, `dcp_profile.py:98`
- [x] Step 7.2: Tests — `tests/test_profile.py:144` (oracle equality, 240 generated profile requests of 1 to 16 cards, with mandatory cards and supersession), `tests/test_profile.py:157` (mandatory card), `tests/test_profile.py:165` (superseded card), `tests/test_profile.py:247`, `tests/test_profile.py:254`, `tests/test_profile.py:261` (no tight certificate, returns `None`), `tests/test_profile.py:196` (contract maximum), `tests/test_profile.py:181` (past deadline returns `None`)
- [x] Step 7.3: Public instances recorded below
- [x] Step 7.4: Gate run, rc=0

#### Public profile instances (from the gate output, `tests/test_profile.py:319` and `tests/test_profile.py:325`)

| Instance | Active | Budget | Utility | Tokens | U | scale | 100*U | 105*utility*scale | solve_profile |
|---|---|---|---|---|---|---|---|---|---|
| `i_9e24f6f61fea4413ac` | 256 | 93 | 78170 | 93 | 78170 | 1 | 7817000 | 8207850 | 0.002 s |
| `i_cf46e9e6258788de2a` | 320 | 2571 | 58666 | 2571 | 1759980 | 30 | 175998000 | 184797900 | 0.074 s |

Both gaps are zero: `U == utility * scale` (78170 * 1 and 58666 * 30 = 1759980), so each selection is proven optimal by its own certificate. For the unit-token instance the test also asserts utility equals the sum of the 93 largest card values. Both certificates pass `checker.check_response` on a full ok response and `checker.certificate_bound` reproduces the `U` above.

#### Contract maximum
`gen.max_request(random.Random(20261011), profile=True)` (500 active cards, budget 8,192): `solve_profile` returned a legal mask in 0.357 s inside the gate and 0.364 s in a separate run on the host (limit 1.5 s). Process `ru_maxrss` went from 20 MB before the call to 24 MB after (decision rows are at most 500 x 8,193 bytes).

#### Issues Encountered
- None blocking. No disagreement found between `resources/director_context_contract.md:124-145` and details section 7; no DR- entry.
- `~/.claude/instructions/python.md` asks for Python 3.12+, `uv` and `ruff`; the plan binds Python 3.11 and the standard library only, so the project rule was followed. `ruff` was not run.
- `gate.log` is not listed by `git status --short`; it was not committed.

#### Discrepancies & Decisions
- DD-P7-1 (2026-10-11): `solve_profile` checks the deadline every 16 items and also returns `None` early when the measured per-item time projects the finish past the deadline, so the caller's fallback keeps the remaining time. Details section 7 only says "finish inside the deadline or return `None`"; this is within it.
- DD-P7-2 (2026-10-11): the certificate uses only the three break-card candidates and `(1, 0)` named in details section 7. It ignores mandatory choices (the contract's relaxation does too), so a request whose mandatory cards are poor value gets no certificate (`tests/test_profile.py:254`); the response is then sent without one.
- DD-P7-3 (2026-10-11): `tests/test_profile.py` is 339 lines against the plan's estimate of about 120; the extra lines are the oracle, deadline and bound-validity tests. No scope beyond the two owned files.

Tests: 22 passed, 0 failed (`python3.11 -m unittest discover -s tests -p 'test_profile.py' -v > gate.log 2>&1; echo rc=$?` gave rc=0, "Ran 22 tests in 1.438s", OK)

---

<!-- end of phase 7 section; do not edit below this line from phase 7 -->


### Phase 8: CLI, pipeline and corpus regression

Status: Complete
Started: 2026-10-11T20:20:59Z (stamp taken when the first file was written; the seat launched a few minutes earlier)
Completed: 2026-10-11T20:30:13Z
Branch: `wip/phase-8-pipeline` @ `38868ebf99d6e0ff7ec96ee4a777a2e2a16edd51` (base `integration` @ `eeb05a2`)

Files Modified (all new; nothing existing was edited):
- `context_solver.py` (60 lines)
- `dcp_pipeline.py` (163 lines)
- `tests/test_cli.py` (256 lines)
- `tests/test_corpus.py` (147 lines)
- `tests/test_differential.py` (154 lines)
- `tests/test_reference_scenarios.py` (69 lines)
- `tests/data/reference_scenarios.json` (byte copy of `docs/reference-scenarios/scenarios.json`, checked with `cmp`)

Steps Completed:
- [x] Step 8.1: `dcp_pipeline.run` and `context_solver.py` per details section 8. Constants as specified (`EXACT_DEADLINE_S` 3.5, `LARGE_DEADLINE_S` 2.5, `MID_SEARCH_DEADLINE_S` 1.0).
- [x] Step 8.2: `tests/test_cli.py`: ok, invalid, infeasible, empty stdin, garbage bytes, oversize input, crash injected in validation, pipeline import failure, KeyboardInterrupt in a solver, run from another working directory.
- [x] Step 8.3: `tests/test_corpus.py`: 28 of 28 public requests through the CLI have the expected status and pass the checker; oracle equality on active counts 2, 3, 3, 12, 16, 18; sample session 61; both profile instances carry a certificate inside 5%. Consistency is reported, not asserted (DD-P8-1).
- [x] Step 8.4: fallback: `solve_large` raising or returning an illegal mask, `solve_exact` raising, both raising in the mid range: response is `ok`, legal, equal to the mandatory closure.
- [x] Step 8.4a: `tests/test_differential.py`: 320 generated requests (active counts 1 to 14, 114 infeasible), 0 disagreements with checker and oracle; 50 single-rule invalid mutations over 34 rules, all answered `invalid`.
- [x] Step 8.4b: contract maximum through the CLI on the host, startup included (from the full gate): coupled 2.554 s, profile 0.496 s; both pass the checker.
- [x] Step 8.5: full gate `python3.11 -m unittest discover -s tests -v > gate.log 2>&1; echo rc=$?` gave `rc=0`.
- [x] Step 8.6: one container trial (`--cpus=2 --network none`): `check_results.py` exit 0, RESULT PASS, max `wall_ms` 2679, p95 (nearest rank, 15 requests with at least 250 active cards) 2679, max `peak_rss_kib` 16828. `LARGE_DEADLINE_S` left at 2.5.
- [x] Step 8.7: `solve_exact` with a 120 s deadline on the host: 36 active proven, 5471, 0.0 s; 48 active proven, 6659, 0.2 s; 64 active proven, 8606, 20.3 s. The CLI's container-trial utilities on the same three instances are 5471, 6659 and 8606, so all three equal the proven optimum.

Issues Encountered:
- The large search is not consistent between presentations of the same problem. Container trial: 61332 / 73602, 72 / 120, 38079 / 49814; none within 0.5%. Known, owned by the search rework (`seat-p6-search-r2`); large-instance utilities here are a snapshot.
- One turn was cut by an API connection drop at 13:28 PDT; no work was lost.

Decisions:
- DD-P8-1: the consistency check on the three repeat pairs and on the permuted copy prints L, H and the ratio verdict but does not fail the gate, as the brief directs. This departs from plan step 8.3, which says "asserted".
- DD-P8-2: the corpus wall-time assertion on the host is 4.0 s, not the 3.5 s in the plan's success criteria, to keep the gate stable on a host shared with other seats. Measured maximum in the gate: 2.734 s.
- DD-P8-3: `dcp_pipeline.LAST_DIAG` (method, active count, proven flag) is added to the interface so the CLI can print the stderr diagnostic line; details section 8 asks for the line but names no carrier.
- DD-P8-4: the test modules share `run_cli`, `one_object`, `encode` and `session_bytes` by importing them from `tests/test_cli.py`.
- DD-P8-5: a solver result replaces the current best only when it is legal and its utility is not lower, so a mid-range exact pass can never lower the search result.

Tests: `python3.11 -m unittest discover -s tests -v`: rc=0, ran 289, passed 289, failed 0, errors 0, skipped 0 (89.8 s). Phase 8 adds 33 of them: `test_cli` 18, `test_corpus` 10, `test_differential` 2, `test_reference_scenarios` 3.

---

<!-- end of phase 8 section; do not edit below this line from phase 8 -->


### Phase 9: Recorded benchmark run
Status: Pending
Started: 
Completed: 

#### Files Modified

#### Steps Completed

#### Issues Encountered

Tests: not run — phase 9 not started

---

<!-- end of phase 9 section; do not edit below this line from phase 9 -->


### Phase 10: README
Status: Pending
Started: 
Completed: 

#### Files Modified

#### Steps Completed

#### Issues Encountered

Tests: not run — phase 10 not started

---

<!-- end of phase 10 section; do not edit below this line from phase 10 -->


### Phase 11: README numbers, ZIP build and clean-extraction check
Status: Pending
Started: 
Completed: 

#### Files Modified

#### Steps Completed

#### Issues Encountered

Tests: not run — phase 11 not started

---

<!-- end of phase 11 section; do not edit below this line from phase 11 -->

