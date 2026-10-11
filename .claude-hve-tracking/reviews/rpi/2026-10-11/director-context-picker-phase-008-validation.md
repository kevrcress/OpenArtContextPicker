# RPI Validation: director-context-picker — Phase 8
Date: 2026-10-11
Plan phase: Phase 8: CLI, pipeline and corpus regression
Coverage: 89% (8 of 9 steps Implemented, 1 Deviated)
Status: Fail (0 Critical, 1 Major, 6 Minor)

Basis: plan Phase 8 and "Requirements added after plan approval", details section 8, the contract, the seat's brief, report and trial table, and the seven Phase 8 files in the `integration` worktree. No research document path was supplied; validated against plan, details and contract. No shell: gate counts (rc=0, 305 tests, 0 skipped on the merged tree) and the `cmp` result are the parent's evidence, not mine. Not read: `dcp_model.is_legal` body, `gen.max_request`, most of `tests/checker.py`. No embedded directives found in the material read.

## Plan Item Comparison

| Plan Step | Changes Log Status | Evidence File | Status |
|---|---|---|---|
| 8.1 pipeline and CLI per details 8 | Found (log:428) | `dcp_pipeline.py:20-24,95-150`, `context_solver.py:8,21-24,34,52` | ✅ Implemented (IV-002) |
| 8.2 `test_cli.py` | Found (log:429) | `tests/test_cli.py:36-44,75-155` | ✅ Implemented |
| 8.3 `test_corpus.py` | Found, deviated (log:430,443) | `tests/test_corpus.py:66-76,82-102,131-143` | ⚠️ Deviated (IV-003, IV-004) |
| 8.4 fallback fault injection | Found (log:431) | `tests/test_cli.py:174-208` | ✅ Implemented |
| 8.4a differential | Found (log:432) | `tests/test_differential.py:16-17,110-150` | ✅ Implemented |
| 8.4b contract maximum via CLI | Found (log:433) | `tests/test_cli.py:229-252` | ✅ Implemented (IV-005) |
| 8.5 full gate | Found (log:434,449) | parent shell evidence | ✅ Implemented |
| 8.6 container trial | Found (log:435) | `seat-p8-pipeline-check-results.txt:50-57,88` | ✅ Implemented (IV-001) |
| 8.7 mid-range 120 s evidence | Found (log:436) | trial table :21,:30,:35 match 8606, 6659, 5471 | ✅ Implemented |
| Reference scenarios (plan:234-243) | Found (log:424-425) | `tests/test_reference_scenarios.py:34-65` | ✅ Implemented (IV-007) |

Success criteria: regression passes (parent); 28 of 28 with status asserted per id (`test_corpus.py:71,76`); oracle equality on 12, 16, 18 (`:90,:93`); host wall criterion of 3.5 s met by measurement (2.734 s, log:444) but gated at 4.0 s.

## Acceptance A1-A10

| Item | Grade | Note |
|---|---|---|
| A1 | Met | 289 on the branch (log:449), 305 merged per parent, 0 skipped; see IV-007 for a silent pass |
| A2 | Met | status per id, not legality alone (`test_corpus.py:54-57,71`) |
| A3 | Met | independent oracle, sample 61 (`test_corpus.py:90,100-101`) |
| A4 | Met | counts and 10 `raw_stdin` asserted (`test_reference_scenarios.py:64-65`) |
| A5 | Met | infeasible above zero asserted (`test_differential.py:133`); 34 rules |
| A6 | Met on the host only | legality without a utility floor; never timed at 2 vCPUs (IV-005) |
| A7 | Met | `test_cli.py:107-121,134-141,174-179` |
| A8 | Met in form | table is a separate file, not pasted; `pass` is shape and legality only (IV-001) |
| A9 | Met | 2679 ms, one run |
| A10 | Weak evidence | prose only, easy family, self-attested `proven` (IV-006) |

## Findings

### IV-001 MAJOR
Plan item: Step 8.6 and the changes-log record.
Evidence: `seat-p8-pipeline-check-results.txt:17,18,20,24,26,32` show utility 120, 223, 72, 136, 128, 72 on 380 to 476 active cards while neighbours score 38079 to 73602 (`:16,:28,:38,:42`). `RESULT: PASS` (`:88`) checks shape, legality and limits, not quality. The report says the cause was not investigated (`seat-p8-pipeline.md:26,37`). The changes log lists only consistency under Issues (changes log:439) and omits this. The table has no `method=` column, so it is not established whether these are search results or the mandatory-closure fallback (`dcp_pipeline.py:82-83,131-133`).
Impact: the contract's main target, 99% of a comparison utility under an all-member gate (`resources/director_context_contract.md:151,157`), may fail on 6 of 15 large instances, and nothing in Phase 8 would show it.
Recommendation: read the recorded stderr `method=` for the six ids; add a dated entry to the Phase 8 log section; hand the ids to `seat-p6-search-r2`; re-measure before Phase 9. The root cause is probably Phase 6's; the missing record is Phase 8's.

### IV-002 MINOR
Plan item: Step 8.1 (details:214,216: after `build_problem` succeeds every failure path answers `ok`).
Evidence: `dcp_pipeline.py:118` and `:135-142` are outside any guard, so an exception there escapes `run` (against its docstring, `:3-5`) and `context_solver.py:43-44` answers `invalid` for a valid feasible request. `json.dumps` at `context_solver.py:34` has the same exit, and the certificate is attached unvalidated (`dcp_pipeline.py:145-147`). A `BaseException` from a solver skips the `except Exception` handlers (`:58-91`) and lands at `:124-126`, discarding the best mask found so far. When `is_legal` itself raises, `p.mandatory` is emitted unchecked (`:128-133`). No test injects a failure in assembly.
Impact: a wrong status under the all-member gate. Graded Minor because the helpers are deterministic and already exercised by `keep`; I found no input that triggers it.
Recommendation: wrap assembly, fall back to a response built from `p.mandatory`, and add one injected test.

### IV-003 MINOR
Plan item: Step 8.3, consistency "asserted".
Evidence: `tests/test_corpus.py:131-143` only prints. Sanctioned at brief:46 and recorded as DD-P8-1 (changes log:443), but not appended to the plan's added requirements (plan:204-243) as CLAUDE.md "Mid-Flow Scope Changes" requires. The brief's AMENDMENTS section reads "(none)" (brief:62); the instruction is in the body. All three pairs fail in the trial (`check-results.txt:55-57`).
Recommendation: add a dated plan entry; restore the assertion after the search rework.

### IV-004 MINOR
Plan item: success criterion, 3.5 s host wall. Evidence: `tests/test_corpus.py:25,129` assert 4.0 s (DD-P8-2, changes log:444). Measured 2.734 s meets 3.5 s. Recommendation: record the change in the plan or restore 3.5 s.

### IV-005 MINOR
Plan item: Step 8.4b. Evidence: `tests/test_cli.py:237-241` assert status, checker and wall only, so a mandatory-only answer passes; only 500 active and 10,000 pairs are asserted (`:245-246`), the chain, cycle, 96 versions and 1,024 features are trusted to `gen.max_request`. Times are host only (changes log:433); the maxima were never run at `--cpus=2`.
Recommendation: assert the remaining maxima and a nonzero selection; time both requests in the container.

### IV-006 MINOR
Plan item: A10 (brief:59), not a plan step. Evidence: the result is prose only (`seat-p8-pipeline.md:21`), with no script, raw output or changes-log entry (changes log:427-449); the family had no requires, groups or pairs (`seat-p8-pipeline.md:36`); `proven=True` is the solver vouching for itself. The unproven-at-3.5 s path never ran through the CLI. Static read: the clock is checked about every 4,096 card visits (`dcp_exact.py:155-161`), leaving roughly 1.4 s to the limit.
Recommendation: keep the generator and timings; add a coupled 24-active case checked against the oracle or a long exact run.

### IV-007 MINOR
Plan item: reference-scenario copy test (plan:240, brief:37). Evidence: `tests/test_reference_scenarios.py:21-23` passes silently when the source is absent instead of calling `skipTest`, so "0 skipped" in the package hides a comparison that did not run. Also the `Tests:` line (changes log:449, 289 tests) describes branch `38868eb`, not the merged tree (305); it needs a dated addition, not a correction.

## Examined, no finding
- Stdout: one write at `context_solver.py:52`; no `print` or `sys.stdout` in any `dcp_*.py`; tracebacks go to stderr.
- Wall limit: every deadline is absolute from `_T0` (`context_solver.py:8`; `dcp_pipeline.py:62,70,80,86`), so no stage gets a second full budget. Work after a deadline is one legality check, the certificate and serialization. Search overshoot measured 25 to 180 ms.
- `infeasible` arises only from `Infeasible` in `build_problem` (`dcp_pipeline.py:110-112`).
- Active count: `p.n` is the contract's count, before usability (`dcp_model.py:22,188-189`; contract:88).
- Profile test matches contract:143 (`dcp_profile.py:26-36`). The empty-session certificate `{"scale":1,"budget_price":0,"feature_prices":{}}` satisfies contract:126-130 and gives U = 0, so `100*U <= 105*utility*s` holds; the profile has no size condition.
- Changes-log claims checked against files: line counts, the 18/10/2/3 test split, constants, 34 mutation rules and trial figures all match. No internal contradiction found in the section.

## Unlisted Changes
N/A - no changed-file list supplied by parent. The seven files the parent named all appear at changes log:419-425.

## Research Coverage
No research document supplied. Contract clauses checked for this phase: process boundary (contract:5) met; response shapes (:107-120) met; certificate schema and profile (:126-145) met; 5 s envelope (:149) met on the public corpus in the container, unmeasured at the contract maxima; quality on larger requests (:151) not evidenced (IV-001).
