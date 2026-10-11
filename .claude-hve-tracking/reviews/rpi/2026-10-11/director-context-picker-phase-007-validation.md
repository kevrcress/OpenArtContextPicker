# RPI Validation: Director context picker — Phase 7
Date: 2026-10-11
Plan phase: Phase 7: Certificate-profile knapsack and certificate
Coverage: 100% (4 of 4 steps Implemented)
Status: Pass (0 Critical, 0 Major, 2 Minor)

Code root read: `.claude/worktrees/integration` (merged state). Paths below are relative to it unless they start with `.claude-hve-tracking/`. This validator has no shell: test results (22 tests rc=0; full suite 305 tests rc=0) are the parent's evidence, not re-run here. `resources/benchmark_inputs.json` was not read, so the public-instance figures are checked for arithmetic only.

## Plan Item Comparison

| Plan Step | Changes Log Status | Evidence File | Status |
|---|---|---|---|
| Step 7.1: `profile_applies`, `solve_profile`, `build_certificate` per details section 7 | Found (changes log :377) | `dcp_profile.py:19`, `dcp_profile.py:39`, `dcp_profile.py:98` | Implemented |
| Step 7.2: tests incl. mandatory card, superseded card, no tight certificate returns `None` | Found (changes log :378), three line citations stale | `tests/test_profile.py:157`, `:165`, `:248`, `:255`, `:262` | Implemented (see IV-001) |
| Step 7.3: record the two public instances' utility, `U/s` and gap | Found (changes log :382-389) | `tests/test_profile.py:303-328` prints the recorded fields | Implemented |
| Step 7.4: run the gate for `tests/test_profile.py` | Found (changes log :380, :404), `discover -s tests -p` form with `rc=0` | 22 `test_` methods counted in `tests/test_profile.py` (5 + 7 + 9 + 1) | Implemented |

Success criteria:
- Oracle equality up to 16 active cards: `tests/test_profile.py:144-155` (240 requests, 1 to 16 cards, mandatory and supersession mixed in), asserting `oracle.best_utility` at `:141`. Met.
- Two public instances pass `checker.check_response` and `100*U <= 105*utility*s` via `checker.certificate_bound`: `tests/test_profile.py:217-230`, `:303-328`. Met. Table arithmetic re-derived: 105 x 78,170 = 8,207,850; 58,666 x 30 = 1,759,980; 105 x 1,759,980 = 184,797,900. All match changes log :386-387.
- 500-card, budget-8,192 request under 1.5 s or `None`: measured 0.357 s and 0.364 s (changes log :392). Met on the idle measurement; not asserted by the test (IV-002).

## Certificate construction against the contract (`resources/director_context_contract.md:126-141`)

- Exact integers: `_bound` at `dcp_profile.py:87-95` uses only integer multiply, add and compare. Candidate choice compares `bound * best[1] < best[0] * scale` (`:126`), cross-multiplied, no division. [HIGH]
- `U` formula: `budget * price` (`:89`) plus `max(0, value*scale - price*tokens)` per card (`:92-94`). `value*scale` equals the contract's `sum(z[f] for f in c.covers)` because `z[f] = weight*scale` and `covers` holds distinct ids (contract `:54`). The feature term is zero for those prices (`:95`). [HIGH]
- Sum over every active card: `values` is built over all of `p.cover` (`dcp_profile.py:105`), whose length is `p.n`, the active count before usability (`dcp_model.py:22`, `:188-205`). Mandatory and unusable cards are included. [HIGH]
- Every feature id present: `zip(p.feat_ids, p.feat_w)` at `dcp_profile.py:137`; `feat_ids` is all request features (`dcp_model.py:193`). Asserted at `tests/test_profile.py:222`. [HIGH]
- Ranges: `1 <= scale <= 1_000_000` and `0 <= price <= scale * sum(weights)` at `dcp_profile.py:123`; each feature price equals its upper limit `weight*scale`, never above it. [HIGH]
- Gap gate: `if 100 * bound > 105 * utility * scale: return None` at `dcp_profile.py:132-133`, with `utility` recomputed from the mask passed in (`:131`). A certificate is returned only when the contract inequality holds. [HIGH]
- Independent recomputation: `tests/checker.py:247-261` computes `U` from the request dict without importing the solver, and agrees in the gated tests. [HIGH]
- Note, not a finding: break-card ordering uses float division (`dcp_profile.py:108`). It only chooses which candidates are tried; `U` and the gate stay exact, so the worst outcome is a missed certificate, never a loose one.

## `profile_applies` against the contract (`resources/director_context_contract.md:143`)

- `contradictions` empty: `dcp_profile.py:26-27`. [HIGH]
- Empty `requires` and null `conflict_group` on every card of the request, active or not: `dcp_profile.py:28-30` iterates `req["cards"]`. Invisible-card case tested at `tests/test_profile.py:113-117`. [HIGH]
- Coverage uniqueness on active cards only: `dcp_profile.py:31-35` over `p.cover`. Superseded-card case tested at `tests/test_profile.py:124-127`. Each result is cross-checked against `checker.is_certificate_profile` at `tests/test_profile.py:96`. [HIGH]

## Findings

### IV-001 [MINOR]
Plan item: Step 7.2 and Step 7.3 evidence citations (record consistency).
Evidence: the changes log cites `tests/test_profile.py:247`, `:254`, `:261` (changes log :378), `:254` again (:401), `:319` and `:325` (:382), and "339 lines" (:402). The file has those tests at `tests/test_profile.py:248`, `:255`, `:262`, `:320`, `:326` and is 340 lines; `:247`, `:254`, `:261` are blank lines. Citations up to `:196` are correct, so one line was added between `:197` and `:247` after the log was written [MEDIUM: inferred, likely the post-review test fix]. No `Correction (2026-10-11)` entry or `superseded` annotation exists in the Phase 7 section.
Impact: six citations point one line early and the section does not mention the later test change; nothing in the code is wrong.
Recommendation: annotate the stale citations and append a dated Correction in the Phase 7 section naming the line added and why.

### IV-002 [MINOR]
Plan item: success criterion "finishes in under 1.5 s on the host or returns `None`".
Evidence: `tests/test_profile.py:202` passes a deadline of `start + 10.0` and `:205-206` assert a non-`None` mask in under 10.0 s, while the changes log (:392) states "(limit 1.5 s)". The 1.5 s figure rests on two one-off measurements. The parent reports 2.4 s on a loaded host, which exceeds 1.5 s with a non-`None` result and is not recorded in the Phase 7 section.
Impact: a slowdown between 1.5 s and 10 s would not fail the gate. Run-time safety is unaffected: the deadline projection (`dcp_profile.py:64-69`) and `dcp_pipeline.py:62` bound the call.
Recommendation: record the loaded-host timing as a dated note in the Phase 7 section. Optionally assert the "under 1.5 s or `None`" form by passing `start + 1.5` and accepting `None`.

## Unlisted Changes
N/A - no changed-file list supplied by parent

## Research Coverage
The parent supplied no research document path for this run. Validated against the plan, details sections 3 and 7, and the binding contract at `resources/director_context_contract.md:124-145`. No research requirements were extracted or invented.

- Plan decision "certificate on profile requests only, omitted when the 5% test fails" (plan :18): met by `dcp_profile.py:132-133`. The caller at `dcp_pipeline.py:143-147` attaches it only when `in_profile` (Phase 8 code, read for context only).
- Details section 7, knapsack: capacity `budget - tokens(mandatory)` (`dcp_profile.py:46`), zero-value cards skipped (`:54`), slice comprehensions (`:70-73`), one `bytes` row per item (`:72`), `None` on deadline (`:56-57`, `:66-69`, `:74-75`). Met.
- Details section 7, certificate candidates: break card and both neighbours over all active cards plus `(1, 0)` (`dcp_profile.py:106-118`, `:110`). Met.
- No contradiction found inside the Phase 7 section. No instruction-like text was found in the `resources/` lines read.
