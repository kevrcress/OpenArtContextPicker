# RPI Validation: Director context picker — Phase 3
Date: 2026-10-11
Plan phase: Phase 3: Independent legality checker, oracle and generators
Coverage: 100% (5 of 5 plan steps Implemented)
Status: Pass (0 Critical, 0 Major, 4 Minor)

Code root read: `.claude/worktrees/integration` (merged state). Static reading only; the validator has no shell. Gate results are the parent's shell evidence (`test_checker_oracle.py` 50 tests rc=0; full suite 305 tests rc=0). Not read: `resources/benchmark_inputs.json` (excluded by the parent). No embedded directives were found in `resources/director_context_contract.md` or `resources/director_session.json`.

## Plan Item Comparison

| Plan Step | Changes Log Status | Evidence File | Status |
|---|---|---|---|
| Step 3.1: `checker.py` per details section 4, sets and dicts | Found (changes log :115) | `tests/checker.py:36`, `:69`, `:103`, `:178`, `:247`, `:264` | Implemented |
| Step 3.2: `oracle.py` exhaustive search over active subsets | Found (:116) | `tests/oracle.py:13`, `:75-88`, `:95` | Implemented |
| Step 3.3: `gen.py` `random_request`, `permute_request` (and `max_request`) | Found (:117, stale line ref) | `tests/gen.py:62`, `:136`, `:208` | Implemented |
| Step 3.4: self-tests pinned to hand-derived values; permute on 30 requests | Found (:118) | `tests/test_checker_oracle.py:156-226`, `:237-271`, `:345-363`, `:556-567` | Implemented |
| Step 3.5: gate run for `tests/test_checker_oracle.py` | Found (:119, rc=0, 45 tests at landing) | parent shell evidence: 50 tests rc=0 on the merged tree | Implemented |

Success criteria:
- Gate passes [HIGH, parent shell evidence]. Test count re-derived by reading: 50 `test_` methods (4+6+11+4+5+4+3+12+1), which equals the parent's figure.
- Sample-session optimum 61 pinned at `tests/test_checker_oracle.py:162`; 7 active cards pinned by name at `:159` [HIGH].
- Seven tiny public requests pinned at `tests/test_checker_oracle.py:177-225` [HIGH].
- Independence [HIGH]: Grep for `dcp` in `tests/checker.py`, `tests/oracle.py`, `tests/gen.py` returns nothing. Their only imports are `__future__` (`checker.py:10`, `oracle.py:8`, `gen.py:7`), `checker` (`oracle.py:10`) and `copy` (`gen.py:9`). The same rule is a test at `tests/test_checker_oracle.py:608-614`.

Pinned values against the research document (all match):
- research :52 i_353b best {a,c} = 60 -> `test_checker_oracle.py:180`. research :55 i_5568 best {b,c} = 70 -> `:185`. research :56 i_f4bb 2 active, answer {b,c} = 70 -> `:192-196`. research :57 and :58 infeasible -> `:198-213`. research :53 and :54 invalid -> `:215-225`.
- research :44 sample walk: 7 active, best 61. Recomputed by hand from `resources/director_session.json:9-22`: portrait + sleeve_detail + closeup + moon = 77 tokens (neon: 79), utility 14+7+6+9+12+8+5 = 61; `amber_arrival` closure costs 27+23+20+32 = 102; 61 is the ceiling because `location` (11) is only on `amber_arrival` and `silhouette` (3) is only on `coat`, which contradicts `sleeve_detail`. The inline copy (`test_checker_oracle.py:19-50`) equals the disk file apart from the omitted `text` fields.
- Certificate arithmetic at `test_checker_oracle.py:348-363` recomputed by hand: 90, 90, 160, 390 and 50. All correct against contract :134-139.

Known deviation, recorded and acceptable: `check_response(..., *, request_valid=True)` at `tests/checker.py:178` (changes log DD-P3-1). The 5 percent gap is not checked by `check_response` (`tests/checker.py:242-243`), as DD-P3-3 states; details section 4 (:126-130) does not ask for it.

## Findings

### IV-001 [MINOR]
Plan item: Step 3.3 (record consistency)
Evidence: Changes log :111 says `tests/gen.py` is "224 lines" with `random_request` (`:53`), `max_request` (`:110`), `permute_request` (`:182`), and :117 cites `tests/gen.py:53`. The file is 250 lines with these at `tests/gen.py:62`, `:136`, `:208`; `tests/gen.py:53` is now inside `_random_pairs`. No `Correction` and no `superseded` annotation exists in the Phase 3 section (:101-141).
Impact: Every `gen.py` citation in the section points at the wrong code.
Recommendation: Annotate :111 and :117 `(superseded — see Correction 2026-10-11)` and append a dated Correction with the current figures.

### IV-002 [MINOR]
Plan item: Step 3.4 and Step 3.5 (record consistency)
Evidence: Changes log :112 says `tests/test_checker_oracle.py` is "560 lines, 45 `unittest` tests" and :137 says "Tests: 45 passed". The file is 618 lines with 50 tests; the five added are at `tests/test_checker_oracle.py:488`, `:513`, `:525`, `:536`, `:541`. :137 is a true record of the landing gate but the log never records the current count. No Correction.
Impact: The log understates the test file and disagrees with the parent's 50-test gate.
Recommendation: Same Correction entry: 618 lines, 50 tests, with the merged-tree gate result.

### IV-003 [MINOR]
Plan item: Step 3.3 (unrecorded post-landing change)
Evidence: `random_request` now raises `ValueError` for out-of-contract arguments (`tests/gen.py:22-25`, `:70-80`), clamps the budget (`tests/gen.py:121-124`) and caps pairs (`tests/gen.py:47`). Details section 4 (:142) says it "Always returns a request". Grep for `gen.py` and for `PR #15` over the whole changes log matches only :111, :117 and :125, so the PR #15 fixes are recorded nowhere, with no DD- entry for the new raise.
Impact: A behaviour change to a test helper used by later phases has no durable record or rationale.
Recommendation: Add a DD-P3-6 entry (or put it in the IV-001 Correction) naming the PR #15 rounds, the two fixes and the five new tests.

### IV-004 [MINOR]
Plan item: Step 3.4 (traceability)
Evidence: Details :152 says the tiny requests are "reproduced inline from the research document", but research :52-58 records only structure and outcomes. The fixture's 10 tokens per card and weights 20/30/40 (`tests/test_checker_oracle.py:62-87`) have no cited source. Outcomes match; equality with the corpus requests is unverified here [MEDIUM].
Impact: Low. The pins prove the checker and oracle on the documented structures, not on the corpus bytes.
Recommendation: State in the log that the tiny fixtures are structural reconstructions, or confirm them against the corpus in a phase that may read it.

No contradiction was found between claims inside the Phase 3 section: DD-P3-1 to DD-P3-5 each agree with the files (`tests/checker.py:192-196`, `tests/oracle.py:19`, `tests/gen.py:91`, `:157-161`, `:183`). All `checker.py` and `oracle.py` line references and sizes at :109-110 are still correct. Not verifiable without a shell: the oracle timings at :126.

## Unlisted Changes
N/A - no changed-file list supplied by parent

## Research Coverage
- Six legal-set conditions (research :39; contract :94-99): met, `tests/checker.py:76-99`, one rejection test each at `tests/test_checker_oracle.py:237-271`.
- Active = visible and not superseded through a chain by a visible card (research :41): met, `tests/checker.py:36-52`, tests `:420-431`.
- Mandatory closure illegal means `infeasible` (research :43, A-06): met, `tests/checker.py:103-106`, `tests/oracle.py:38`, agreement over 120 requests at `tests/test_checker_oracle.py:445-464`.
- Certificate sum over active cards only (A-17): met, `tests/checker.py:252-258`, test `:358`.
- Contract maxima absent from the public corpus (research :86): met by `gen.max_request`, tests `:583-605`.
- Not pinned, and not required by the plan: 18 legal sets, the two tied optima and the "newest revision wins" score 58 (research :44).
