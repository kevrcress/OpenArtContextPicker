# RPI Validation: Director context picker — Phase 5
Date: 2026-10-11
Plan phase: Phase 5: Exact search for 24 or fewer active cards
Coverage: 100% (3 of 3 steps)
Status: Pass (0 Critical, 0 Major, 7 Minor)

Scope: static reading only (no shell). Code root `.claude/worktrees/integration`. Test outcomes are the parent's shell evidence (suite rc=0, 305 tests; `test_exact.py` 15 tests rc=0), not re-run here. `resources/benchmark_inputs.json` was not read, so the active counts of the three public small instances (12, 16, 18) are unverified. No embedded directives were seen in the files read.

## Plan Item Comparison

| Plan Step | Changes Log Status | Evidence File | Status |
|---|---|---|---|
| Step 5.1: implement `solve_exact` per details section 5 | Found (changes.md:253), with recorded decisions DD-P5-1..5 | `dcp_exact.py:63` | Implemented (recorded, sound deviations) |
| Step 5.2: oracle comparison tests and 24-card stress test | Found (changes.md:254), line citations stale | `tests/test_exact.py:227`, `tests/test_exact.py:271` | Implemented |
| Step 5.3: run the gate for `tests/test_exact.py` | Found (changes.md:255, :273), count stale | parent evidence: 15 tests rc=0 | Implemented |

Success criteria (plan:89):
- At least 300 oracle-equal, proven cases at 1 to 16 cards: `tests/test_exact.py:227-239` (420 draws, floor of 300 asserted at :239; supersession, versions, groups, pairs, mandatory all drawn at :232-237). Met.
- Three public small instances and sample session: `tests/test_exact.py:254-267`. Met (instance sizes unverified, see Scope).
- At least 40 cases at exactly 24 active, proven under 1.5 s: `tests/test_exact.py:271-294` (80 cases, `p.n == 24` at :280, limit at :283); the plan's three families are in `FAMILIES` at :131-137. Met.
- Step 5.2 guard (strengthen and record worst time): recorded at changes.md:258-259 (1.065 s probe, 0.308 s in gate). Met.

## Soundness review (details section 5)

- Eligible set, `dcp_exact.py:171`: not in S, not in X, `closure_conflict[c] & S == 0`, `tokens[c] <= room`. Any legal extension T of S contains `closure[c]` for each added c, and no member of it conflicts with T, so `closure_conflict[c] & S == 0` holds for every addable card. X is closed under `dependents` (transitive closures), so "c not in X" already implies `closure[c] & X == 0`. The set still contains every addable card: DD-P5-1 is valid [HIGH].
- Dropping cards with gain <= 0 for the whole subtree (`dcp_exact.py:180`): weights are 1 to 1,000 (`dcp_validate.py:185`), so zero gain means no uncovered feature; such a card adds nothing unless required, and required cards enter through `closure[branch]` (`dcp_exact.py:219-233`), not through the candidate list. Valid [HIGH].
- Gain-sum prune (`dcp_exact.py:185`) and bound (b) (`dcp_exact.py:188-200`): coverage is subadditive and an added set costs the sum of its own tokens, so the positive-gain added cards form a feasible knapsack; Dantzig order with a break at the first non-fitting item and an integer floor is the standard valid bound. Float ratio ordering is exact here: gain <= 1,024,000 and tokens <= 512 (contract lines 53, 56), far below 2^52, so only true ties collide. Valid [HIGH].
- Bound (a) (`dcp_exact.py:205-212`): union of `cover[c]` over the same eligible positive-gain items, minus covered; byte tables (`dcp_exact.py:128-142`) sum `feat_w` correctly and masks are confined to `relevant`. Skipping it on 15 nodes in 16 cannot lose optimality. Valid [HIGH].
- Stale-gain carry (`dcp_exact.py:173-179`, :217, :232): exclude child gets adjusted gains with stale 0; include child gets `gain_mask`, which is disjoint from the earlier covered set. Correct [HIGH].
- Branching (`dcp_exact.py:214-233`): exclude child is always pushed; include child only when closure avoids X and fits. Complete partition [HIGH].
- Deadline: clock read at the first node (`dcp_exact.py:148`, :158-161) and per greedy round (`dcp_exact.py:35`); a cut returns `(best_mask, False)`; `proven` True only on stack exhaustion (:234) or no usable cards (:121-122).
- Incumbent contract: used only when `is_legal` (`dcp_exact.py:112`); the result never falls below it; every returned mask is legal by construction. Tests at `tests/test_exact.py:343-392`.

## Findings

### IV-001 [MINOR]
Plan item: Step 5.2 / 5.3 record
Evidence: changes.md:250 and :273 say `tests/test_exact.py` is 314 lines with 11 tests; the file is 408 lines with 15 tests (`tests/test_exact.py:408`). changes.md:254 cites `:171` (oracle) and `:230` (stress); those are now a helper boundary and a loop body; the tests are at `tests/test_exact.py:211` and `:270`. No dated Correction in the section.
Impact: the record cannot be graded Complete under the Corrections rule.
Recommendation: annotate the three claims `(superseded — see Correction 2026-10-11)` and append a Correction with the post-review counts and lines.

### IV-002 [MINOR]
Plan item: Step 5.2 record
Evidence: changes.md:275 says non-knapsack 24-card cases have "no independent optimum check"; `tests/test_exact.py:297-308` and `:310-324` now check 25 such cases against a hand value and the oracle.
Impact: the log understates the evidence and contradicts the file.
Recommendation: same Correction entry as IV-001.

### IV-003 [MINOR]
Plan item: Step 5.2 (deadline test)
Evidence: changes.md:260 records a 0.07 s limit; the test now sets a 0.05 s deadline and asserts 0.25 s (`tests/test_exact.py:364-368`), a 200 ms tolerance, and does not assert `proven`.
Impact: the gate would pass an overshoot 100 times larger than the log claims; the loosening is unrecorded.
Recommendation: record the change; tighten to about 0.10 s if the Docker host allows.

### IV-004 [MINOR]
Plan item: Step 5.1 (DD-P5-2)
Evidence: changes.md:267 says a node costs about 1 ms at 500 cards and that the overshoot stays "near 1 ms at any size"; with a read every 4,096 visits and 516 counted per node (`dcp_exact.py:157-158`) that is about 8 nodes, so about 8 ms by the entry's own figure. The comment at `dcp_exact.py:155-156` repeats the claim.
Impact: internal contradiction; harmless against the 2.5 s and 3.5 s deadlines (`dcp_pipeline.py:21-22`).
Recommendation: Correction stating "under about 10 ms" or a measured figure.

### IV-005 [MINOR]
Plan item: Step 5.1 (DD-P5-5)
Evidence: changes.md:270 leaves "weights never negative" at [MEDIUM], unchecked. It is true: `dcp_validate.py:185` rejects weights below 1. Tokens are at least 1, so the zero-cost `inf` branches at `dcp_exact.py:50` and `:183` are dead.
Impact: an open assumption in a soundness-relevant decision.
Recommendation: raise to [HIGH] by Correction; the dead branches can stay.

### IV-006 [MINOR]
Plan item: Step 5.2 guard (time margin)
Evidence: changes.md:259 and :262 give worst 1.065 s on the host and "no timing inside Docker". The parent's later evidence is 1.88 s worst (10 of 10 proven) at --cpus=2, above the plan's 1.5 s host figure and inside the 3.5 s deadline (`dcp_pipeline.py:21`). On a cut the 24-card path returns the best set found with `proven` False and no other fallback (`dcp_pipeline.py:68-76`).
Impact: residual risk only; a hidden wide-coverage instance about 1.9 times slower than the worst seen would lose exactness (contract line 151). No failing case is known.
Recommendation: Correction recording the Docker figure; widen the Docker sample of the coverage family beyond 10.

### IV-007 [MINOR]
Plan item: phase process
Evidence: changes.md:271 records that `python.md` and `python-tests.md` were not read.
Impact: conventions compliance is unverified for `dcp_exact.py` and `tests/test_exact.py`.
Recommendation: one conventions pass before the ZIP build.

## Unlisted Changes
N/A - no changed-file list supplied by parent. `gate.log` exists in the code root and is ignored (`.gitignore:15`), matching changes.md:261.

## Research Coverage
A research document exists (plan:4) but was not supplied for this run; validated against the plan, details sections 3 and 5, and contract lines 90-122 and 151.
- Exact maximum for at most 24 active cards (contract line 151): search is sound and complete given time. Met, subject to IV-006.
- Legal set always returned, at least the mandatory closure (contract lines 92-101): Met.
- No recursion, depth up to 500 (details section 5): explicit stack, `dcp_exact.py:152-153`; test at `tests/test_exact.py:394`. Met.
- Deadline every 256 nodes (details section 5): deviated by DD-P5-2 to a work counter; recorded and justified.
