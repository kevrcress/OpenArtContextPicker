# Planning Log: Director context picker

## Discrepancies

### DR-001: Mid-range quality target
Source: Research "Ambiguities" A-10 and "Contradictions between sources": docs/orchestrator-notes.md says the contract names no target between 25 and 249 active cards; contract :151 words the 99% target for all "larger assessed requests".
Resolution: The plan holds 25 to 249 active cards to the 99% reading. Phase 8 runs the exact search after the heuristic for up to 64 active cards with the time left.
Status: Resolved

### DR-002: Class counts in the orchestrator notes
Source: Research "Corpus": 7 tiny and 13 large coupled by measured active count; the notes say 9 and 11.
Resolution: The plan uses the measured counts (15 instances in the efficiency workload). The notes are the owner's file and are not edited by this plan; the correction is listed in the research follow-on.
Status: Resolved

### DR-003: Recorder dry run executed during planning
Source: docs/research-prompt.md forbids executing supplied files during research.
Resolution: The dry run happened in the plan phase, at 12:42 PDT, on copies in a scratch directory, to satisfy the global rule that a verbatim command in a plan is run before validation. `resources/` was not touched.
Status: Resolved

### DD-001: Order of validation and legality in the dependency graph
Source: Owner instruction: "Order within the dependency graph: strict input validation, legality, exact search for 24 or fewer active cards, then the large-instance method."
Assumption: Validation (Phase 1) and the legality core (Phase 2) have no dependency on each other because the model takes an already-validated plain dict, so both start in the first wave together with the oracle and checker (Phase 3). Exact search (5) precedes nothing but shares a wave with the large method (6); Phase 8 wires them in the stated order.
Risk: If the first wave slips, integration priority is 1, 2, 3, then 5, then 6 and 7.

### DD-002: 750 ms p95 with 64 MiB declined
Source: Research "Corpus": six unit-weight large instances; the 99% bar allows a deficit of one to four cards.
Assumption: More search time buys main quality; the optional latency target is traded away. Measured p95 and RSS are still reported.
Risk: If the 0.3 s results in `tools/tune_search.py` equal the 2.0 s results on every instance, the decline cost nothing in quality but forfeited an optional capability. Step 6.4 records the data either way; the decision is not revisited after Phase 8 because a constant change after review forces a re-review.

### DD-003: Certificate only on profile requests
Source: Contract :143, :145.
Assumption: A certificate on a non-profile request earns nothing and a malformed one is a risk to nothing but the optional capability; emitting it only where it is assessed keeps the response minimal.
Risk: None to core fields (contract :145).

### DD-004: `benchmark_inputs.json` ships in the ZIP
Source: Research open question 1.
Assumption: 922,249 bytes zipped is acceptable to the submission channel.
Risk: An upload size limit below about 1 MB. Mitigation: `tools/make_zip.py` takes an `--exclude-inputs` flag; the README then tells the reader to place the public corpus beside the solver.

### DD-005: Time-bounded search is not deterministic
Source: Contract :7 ("Equivalent inputs may choose different tied optima"), A-18.
Assumption: A wall-clock deadline is safer against the 5 s limit on unknown hardware than a fixed iteration count. Two runs of one request can return different legal sets.
Risk: Utility spread between runs; measured by the consistency test and the reference runs.

### DD-006: Last-resort response when validation itself crashes
Source: Research A-16.
Assumption: An unexpected exception inside validation is far more likely to come from malformed input than from a valid request, so it maps to `invalid`. After validation has passed, no path returns `invalid` or `infeasible` except the mandatory-closure rule.
Risk: A validator bug on a valid request would answer `invalid`. Mitigated by the rule tests and by running all 28 public requests.

### DD-007: Non-roster agent for tracker syncs
Source: CLAUDE.md "Subagent Dispatch Discipline".
Assumption: gh-tracker syncs run in a `general-purpose` subagent on the sonnet tier, because they are mechanical GitHub bookkeeping that would otherwise block the parent.
Risk: A sync mistake; each sync's result is checked against `gh` output by the parent before the next one.

<!-- Entries below appended by hve-plan-validator, 2026-10-11. Static read only: the validator has no shell, so nothing below was executed. -->

### DR-004: Post-run check does not assert the recorded limits
Source: Research R-02, R-03, R-86, R-87, R-94 and follow-on at research :333 ("every `timed_out` false, every `response_parse_error` null, every `exit_code` 0"); research :143 (a record can show `wall_ms` over 5000 with `timed_out` false).
Gap: Details section 9 (details :223) makes `tools/check_results.py` assert only the hashes, `python_sources_unchanged`, `quota_vcpus`, the record count and the checker verdict. `wall_ms`, `peak_rss_kib` and `timed_out` are printed, not asserted. `exit_code`, `response_parse_error` and the raw `stdout` shape (one object, one trailing newline) are not read at all. Phase 9 and Phase 11 success criteria rest on this script's exit code.
Severity: Major
Recommendation: Add to details section 9: exit 1 when any record has `timed_out` true, `exit_code != 0`, `response_parse_error` not null, `wall_ms >= 5000`, `peak_rss_kib >= 262144`, or a raw `stdout` that is not exactly one JSON line. State how `check_response` is called when `response` is null.
Status: Open

### DR-005: No randomized differential test of the ok / infeasible decision
Source: Research R-67 ("property test against the checker"), R-65, A-06, contract :101, :157 (a wrongly infeasible response fails its group).
Gap: Phase 5's generated set is restricted to "infeasible-free cases" (plan :90). Phases 2 and 8 test `Infeasible` only with hand-built cases and the 28 public requests. Nothing compares `build_problem` (active set, `n`, `Infeasible`) with `checker.active_cards` / `checker.expected_feasible` on generated requests, although `gen.random_request` already has `n_mandatory`, `p_supersede` and `n_versions`.
Severity: Major
Recommendation: Add a step to Phase 8 (`tests/test_cli.py` or `tests/test_corpus.py`): several hundred `random_request` cases with mandatory cards, supersession and several versions run through `dcp_pipeline.run`, each response passed to `checker.check_response`, and `Problem.n` compared with `len(checker.active_cards(req))`.
Status: Open

### DR-006: Contract-maximum sizes are not tested on the coupled path
Source: Research :86 ("never reaches contract maxima ... own tests must cover these") and follow-on :332.
Gap: Maxima are exercised for validation (500 cards, plan :40) and the profile knapsack (500 by 8,192, plan :116) only. No test runs the CLI end to end on a coupled request at 500 active cards, 10,000 pairs, 1,024 features, 64 covers per card, 96 versions, budget 8,192, with a long `requires` chain and a large cycle. `build_problem` is timed only on the largest public instance (488 cards, closure size 4). A timeout there fails a whole group.
Severity: Major
Recommendation: Add one generated contract-maximum request (plus a 500-deep `requires` chain variant) to `tests/test_cli.py` with a wall assertion well under 5 s, and a matching `build_problem` timing in step 2.3.
Status: Open

### DR-007: Evidence for the 99% bar comes from the same algorithm
Source: Research open question 3 ("the only evidence available is an upper bound and agreement between independent search runs"), R-90.
Gap: Step 6.4 compares a 2.0 s run with 20 s runs of the same `solve_large` at three seeds. No upper bound is computed for any coupled instance and no independent method is used, so a systematic weakness of the search is invisible. The three mid instances (36, 48, 64 active) are small enough for a long offline `solve_exact` run.
Severity: Minor
Recommendation: In `tools/tune_search.py`, add a long `solve_exact` run for the three mid instances and print a relaxation upper bound per large instance (the certificate formula at its best price, via `checker.certificate_bound`). Report both in the README as the stand-in evidence.
Status: Open

### DR-008: MUST rows with a rule but no named test
Source: Research R-05, R-15, R-21, R-34, R-42, R-75, R-85, A-14.
Gap: The rules exist in the details file or follow from the pipeline order, but no plan step names a test for: no file created in cwd (R-05); one id reused across the four namespaces is valid (R-15); child version listed before its parent is valid (R-21); `text` changes leave status and utility unchanged (R-34); an ancestor's card superseding a descendant's card is invalid (R-42, reverse direction); a request both invalid and infeasible answers `invalid` (R-75); import scan for standard library only (R-85); `-0` accepted as zero (A-14).
Severity: Minor
Recommendation: Add these cases to steps 1.2 and 8.2; add a `grep -n "^import\|^from"` scan over the root `.py` files as a Phase 8 step.
Status: Open

### DR-009: A-15, A-18, A-19 cannot be checked from the consolidated research
Source: Research "Ambiguities" lists A-01 to A-14, A-16, A-17, A-20 only ("the ones that change code"). DD-005 cites A-18.
Gap: A-15, A-18 and A-19 live only in the gitignored subagent artifact. The seventeen listed ambiguities are each covered by details section 2, 3, 7 or 8.
Severity: Minor
Recommendation: Parent confirms from `.claude-hve-tracking/research/subagents/2026-10-11/director-context-picker-contract.md` that A-15, A-18 and A-19 need no code, or adds them to the plan.
Status: Open

### DD-008: Per-phase gate command cannot import the test helpers
Source: Details section 1 (details :34): "`discover -s tests` puts `tests/` on it (helpers import as `import checker` ...). A phase runs only its own test file ...: `python3.11 -m unittest tests/test_validate.py -v`." Plan steps 3.5, 5.3, 6.5, 7.4.
Assumption: That the file-path form gives the same `sys.path` as discovery. It does not [MEDIUM, from `unittest` behaviour, not executed]: `python -m unittest tests/test_exact.py` imports the file as `tests.test_exact` with only the current directory on `sys.path`, so a bare `import checker`, `import oracle` or `import gen` raises `ModuleNotFoundError`. The claim has no confidence marker and no command output beside it.
Risk: The gates of phases 3, 5, 6 and 7 fail at import as written. Each parallel implementor then invents its own fix (a `sys.path` shim, `from tests import checker`), and those fixes can break under the README's `discover -s tests` command.
Severity: Major
Recommendation: Parent runs a two-file probe before dispatch and pastes command and output into the plan. Likely fix: per-phase gate `python3.11 -m unittest discover -s tests -p 'test_exact.py' -v`.
Status: Open

### DD-009: Dependencies that exist in fact but are not declared
Source: Plan Phase 4 (`Dependencies: none`), Phase 8 (`Dependencies: Phase 1, 5, 6, 7`), Phase 10 (`Dependencies: Phase 8`), wave statement at plan :34.
Assumption: That Phase 4 is finished before anything needs it.
Risk: (1) Phase 4 needs Phase 3: `tools/check_results.py` imports `tests/checker.py`, and both the success criterion ("exits 1 on the stub") and step 4.3 cannot be met until it exists. (2) Phase 8 needs Phase 4: step 8.6 runs `tools/build_package.py`, `tools/run_recorded.sh` and `tools/check_results.py`, and the full discover gate in step 8.5 runs `tests/test_tools.py`. The wave rule lets 8 start with 4 unfinished. (3) Phase 10 needs Phase 4: step 10.2 runs the README's package and Docker commands. Phase 8's direct use of Phases 2 and 3 is covered transitively.
Severity: Major
Recommendation: Declare Phase 4 -> Phase 3 (or split `check_results.py` into a later phase), Phase 8 -> Phase 4, Phase 10 -> Phase 4, and update the wave statement.
Status: Open

### DD-010: The mid-range exact pass gets no time
Source: Details section 8 (details :206): "`solve_large(p, t0 + LARGE_DEADLINE_S)`, then when `p.n <= MID_EXACT_MAX_ACTIVE` `solve_exact` with the heuristic result as incumbent and the same deadline." Details section 6 (details :173): improvement runs "until the deadline". DR-001's resolution relies on this pass.
Assumption: That time is left after `solve_large` returns.
Risk: If "the same deadline" is `t0 + LARGE_DEADLINE_S`, `solve_large` has already consumed it and `solve_exact` exits at its first clock check, so 25 to 64 active cards get the heuristic only. If it means `EXACT_DEADLINE_S`, the text does not say so. Related gap: the deadline passed to `solve_profile` is not stated anywhere in section 8.
Severity: Major
Recommendation: Fix the split in details section 8, for example `solve_large` until `t0 + 1.0` when `p.n <= 64`, then `solve_exact` until `t0 + EXACT_DEADLINE_S`; name the `solve_profile` deadline.
Status: Open

### DD-011: Fallback is undefined when the model build fails or a step overruns
Source: Details section 8 (details :207, :209); research A-16.
Assumption: That every failure after validation happens inside a solver, where `p.mandatory` is available, and that every component honours its deadline.
Risk: An unexpected exception inside `build_problem` (not `Infeasible`) leaves no `Problem`, so "the mandatory-closure answer" cannot be produced; the text does not say what is printed. There is no hard backstop (for example `signal.setitimer` near 4.3 s that emits the best mask so far), so one loop that misses its clock check ends in SIGKILL and no output.
Severity: Minor
Status: Open

### DD-012: Underspecified points in the exact and local search
Source: Details section 5 (details :158-160) and section 6 (details :173).
Assumption: That an implementor fills these the sound way.
Risk: (1) "tokens fit" must charge `mask_tokens(closure[c] & ~S)`, not `closure_tokens[c]`, or shared requirements are charged twice and exactness is lost (R-61). (2) "still-eligible" is not defined; both bounds are valid only if it means every usable card not in `S | X`, with any further filter monotone in S. (3) Bound (b) must use integer floor arithmetic; a float that rounds down can prune the optimum. (4) "Pick a card c outside S" must read "a usable card", otherwise the eviction argument fails. (5) Section 6 "check the clock at most every 32 moves" should read "at least".
Severity: Minor
Status: Open

### DD-013: Shared and unowned files
Source: Plan steps 1.3, 2.4, 3.5, 5.3, 6.5, 7.4 (`> gate.log`); plan step 11.4; details :26 ("gitignored").
Assumption: That `gate.log` and `.gitignore` need no owner.
Risk: Phases 1 to 4, and later 5 to 7, run in parallel and all redirect to the same `gate.log`, so a failing phase can read another phase's log. No phase owns the `.gitignore` edit for `director-context.zip`, `gate.log` and `build/`. Step 11.4 expects ignored files to appear in `git status --short`, which does not list them.
Severity: Minor
Status: Open

### DD-014: Confidence markers and evidence gaps
Source: Plan step 4.1; Phase 2 and Phase 7 success criteria; step 8.6; plan :27, :29, :102.
Assumption: Several timing and environment assumptions are stated without a marker.
Risk: (1) Step 4.1 marks `[HIGH]` an interface in a file that does not exist yet; by CLAUDE.md that is `[MEDIUM]`. (2) No marker on: `build_problem` under 60 ms; the 500 by 8,192 DP under 1.5 s; host timings standing in for the container in step 8.6. (3) Plan :27 elides part of the container command with `...`; plan :29 gives "`zip -9`" with no full command line. (4) Plan :102 says 16 public instances have at least 25 active cards; the research table gives 18 (3 mid, 13 coupled, 2 unconstrained). (5) The search budget reads 2.0 s (Phase 6 criterion), 2.5 s (details section 8) and "not above 3.0 s" (step 6.4) without saying which clock each uses.
Severity: Minor
Status: Open

### Validator notes (no discrepancy; reasoning recorded for the review phase)
- Details section 2 against contract :40-:78: every row of the limits table, the key-set rules, integer notation, boolean, non-finite, null, supersession ancestry and pair rules are present and match. No wrong rule found.
- Details section 3 `usable` and `Infeasible` (details :112-113) against contract :78, :86, :94-101: complete. Every card of any legal set outside `mandatory` satisfies all four `usable` tests, and the four `Infeasible` causes are exactly the ways the mandatory closure can break conditions 1 to 6.
- Excluding via `X |= dependents[c]` is sound: a selected j with c in `closure[j]` would force c into S. The include/exclude branching reaches every legal set.
- Bound (a) is valid because coverage of any extension lies inside the union of eligible covers. Bound (b) is valid because coverage is subadditive and each added card costs its own tokens, so the extension is a 0/1 knapsack whose LP value bounds it. Both subject to DD-012 points 2 and 3.
- Certificate (details :190): with `z[f] = w*s` every range holds, any nonnegative `p` gives a valid bound by weak duality, the sum runs over all active cards as contract :136 requires, and the exact `100*U <= 105*utility*scale` test gates emission. It cannot emit a schema-invalid or loose certificate; it can only return `None`.
- Optional capabilities: all four carry an explicit yes or no (plan :16-21). Oracle, checker, Docker harness, recorded run, README and ZIP build each have an owning phase.
