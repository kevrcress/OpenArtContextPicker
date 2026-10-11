# RPI Validation: Director context picker — Phase 2
Date: 2026-10-11
Plan phase: Phase 2: Model and legality core
Coverage: 100% (4 of 4 steps Implemented)
Status: Pass (0 Critical, 0 Major, 4 Minor)

Scope and method: read plan Phase 2 (plan:48-58) plus "Requirements added after plan approval" (plan:204-243), changes log Phase 2 section only (changes:54-98), details section 3 (details:70-116), contract lines 64-101, and both owned files in full in `.claude/worktrees/integration`. No shell: test pass/fail and the sample-session values rest on the parent's evidence (`test_model.py` 55 tests rc=0; full suite 305 tests rc=0; 102/102 reference scenarios and 400 generated requests with 0 disagreements). `resources/benchmark_inputs.json` and `resources/director_session.json` were not read. Contract text treated as data; no embedded directives found in lines 64-101.

## Plan Item Comparison

| Plan Step | Changes Log Status | Evidence File | Status |
|---|---|---|---|
| Step 2.1: `Infeasible`, `Problem`, `build_problem`, mask helpers per details section 3 | Found (changes:72) | `dcp_model.py:13`, `:18`, `:180`, `:305-367` | ✅ Implemented |
| Step 2.2: tests for every listed case | Found (changes:73) | `tests/test_model.py:62-527` (55 methods, 8 classes, counted) | ✅ Implemented |
| Step 2.3: timing on `i_3b971612ce637e324b`, recorded in the changes log | Found (changes:74) | changes log only; no file artifact (see IV-001) | ✅ Implemented |
| Step 2.4: gate for `tests/test_model.py` | Found (changes:75, :94) | parent shell evidence: 55 tests, rc=0 | ✅ Implemented |

Success criteria (plan:52): gate passes — met (parent rc=0). Sample session `n == 7`, closures, usable set — pinned at `tests/test_model.py:461-489`, met via the passing gate. `build_problem` under 60 ms — claimed 3.05/3.25/5.08 ms (changes:74), record only (IV-001).

Step 2.2 case map (`tests/test_model.py`): merge head :62; invisible branch :70; supersession chain :94; superseded superseder still deactivates :102; invisible superseder :115; `requires` on inactive :139 and invisible :149; cycle :165; self-requirement :181; pair in closure :236; same group in closure :244; inert pair :251; mandatory inactive :304, pair :323, over budget :335; empty mandatory at budget 0 :358; six conditions :397 (1), :405 (2), :409 (3), :412 (4), :415 (5), :418 (6), each isolating one violation; sample numbers :461-527.

Interface check against details section 3: the 15 `Problem` fields match in name, annotation and order (`dcp_model.py:21-35` vs details:82-96); frozen dataclass (`dcp_model.py:17`); `Infeasible` docstring verbatim (`dcp_model.py:14`); all seven public signatures identical (`dcp_model.py:180`, `:305`, `:310`, `:321`, `:326`, `:348`, `:359` vs details:98-104). Field comments are shortened, not changed. Standard library only (`dcp_model.py:8-10`); tests do not import `dcp_validate` (`tests/test_model.py:5-10`). All 12 `file:line` anchors in changes:62-69 resolve in the merged tree; file lengths 367 and 531 match.

Contract semantics, traced statically:
- Visibility (contract:82): head plus ancestors, explicit stack — `dcp_model.py:38-48`.
- Active (contract:84): visible and not reachable via `supersedes` from a visible card; a superseded superseder still deactivates; invisible cards never seed the walk — `dcp_model.py:56-69`.
- Closure (contract:64, :86, :96): iterative Tarjan over `requires` of all cards; a component containing or reaching a non-active card is dead, closure 0, no redirect — `dcp_model.py:137-151`, `:161-162`. Components finish sinks first, so `comp_of[nxt]` is always defined at `:146`.
- Conflicts (contract:76-78, :97-98): groups over active cards excluding self `:206-214`; pairs only when both endpoints are active, symmetric, no transitivity, no transfer `:215-220`.
- Infeasible (contract:78, :101): mandatory not active `:260`, closure leaves active set `:262`, internal clash `:265-266`, over budget `:268-269`; nothing else raises it. Empty mandatory gives `mandatory == 0`, feasible at budget 0.
- Usable (details:112): the four exclusions at `:274`, `:277`, `:279-284`, shared cards charged once; unusable cards stay in `n` (contract:88) since `n = len(ids)` at `:189`.
- `is_legal` (contract:92-99): range guard `:328`, mandatory `:330`, closure and conflict `:341`, budget with equality `:345`.

DD-P2-1, DD-P2-2, DD-P2-3 (changes:89-91) each match the code (`dcp_model.py:228`, `:328`, `:260-269`). Scope estimate in plan:51 was about 220 + 250 lines; actual is 367 + 531 (not a finding).

## Findings

### IV-001 MINOR
Plan item: Step 2.3 and the under-60 ms success criterion.
Evidence: changes:74 gives the numbers but describes the command only as "a `python3.11 -c` one-liner"; changes:86 confirms no timing assertion exists in `tests/test_model.py`. The parent supplied no re-run.
Impact: the criterion is recorded but not reproducible from the artifact. Risk is low: the claim has about 12x headroom and the build is linear in cards, pairs and closure sizes.
Recommendation: parent reruns the timing once and appends the verbatim command and output to the Phase 2 section.

### IV-002 MINOR
Plan item: Step 2.3 (record consistency).
Evidence: changes:74 says "Worst single first-call build over all 28 public instances: 3.78 ms"; changes:83-85 say one instance raises `ValueError`, two raise `Infeasible`, and "25 public instances that build". No dated Correction.
Impact: the 28-instance timing figure covers three calls that do not complete a build; the reader cannot tell what was timed.
Recommendation: annotate changes:74 `(superseded — see Correction 2026-10-11)` and state "28 calls, 25 completed".

### IV-003 MINOR
Plan item: Phase 2 record versus plan:212 (one pull request per phase).
Evidence: changes:59 says the files were "left uncommitted" in worktree `agent-ad673c08bd763aad8`; they are now in the merged tree at identical line numbers (`dcp_model.py:13`, `tests/test_model.py:1`), and the parent reports PR #13 merged. The section names no branch, PR or commit.
Impact: the section's landing state is stale and has no trace to PR #13 or its review.
Recommendation: append a dated Correction naming PR #13 and its merge; leave the original sentence annotated.

### IV-004 MINOR
Plan item: Step 2.2, sample session numbers.
Evidence: research:44 records 18 legal sets, exactly two tied optima and 77 or 79 tokens. `tests/test_model.py:505-520` asserts `best == 61` and membership with `assertIn` only; a third tied optimum or a wrong legal-set count would pass.
Impact: three hand-walk facts are unpinned. The success criterion (n, closures, usable) is met.
Recommendation: optionally assert `len(winners) == 2`, 18 legal masks, and tokens 77 and 79.

## Unlisted Changes
Both Phase 2 files on the parent's list (`dcp_model.py`, `tests/test_model.py`) are in the Phase 2 section (changes:62-69). The other 26 files were not compared: the parent limited this run to the Phase 2 section, and the list uses globs (`tests/*`, `tools/*`). Whole-log comparison stays with the parent.

## Research Coverage
- Legal-set conditions 1 to 6 (research:39; R-59 to R-65): met — `dcp_model.py:326-345`, `tests/test_model.py:397-421`.
- Active definition and count before usability (research:41-42; R-54 to R-58): met — `dcp_model.py:51-69`, `:189`; `tests/test_model.py:94-135`.
- Unusable closures: inactive member, pair, same group (A-12), over budget (research:43; R-51, R-57): met — `dcp_model.py:271-284`; `tests/test_model.py:139-163`, `:236-249`, `:295`.
- Mandatory closure illegal gives infeasible, else legal (research:43; A-06, R-52, R-65): met — `dcp_model.py:255-269`; `tests/test_model.py:304-348`.
- Cycles and self-requirement (R-40): met — `tests/test_model.py:165-186`. Inert and non-transferred pairs (R-50): met — `tests/test_model.py:251-267`.
- Sample session (research:44): n, closures, usable, best 61 pinned; legal-set count and optimum count not pinned (IV-004).
- Census cross-check: 488 cards, 7,424 pairs, 476 active in changes:74 match research:77; the `ValueError` instance in changes:83 is the invalid three-element pair of research:54; two `Infeasible` instances in changes:84 match research:57-58.
