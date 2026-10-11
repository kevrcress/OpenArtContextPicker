# Review Log: Director context picker (`director-context.zip`)
Date: 2026-10-11
Plan: .claude-hve-tracking/plans/2026-10-11/director-context-picker-plan.md
Changes: .claude-hve-tracking/changes/2026-10-11/director-context-picker-changes.md
Research: .claude-hve-tracking/research/2026-10-11/director-context-picker.md
Overall Status: at validation time ⚠️ Needs Rework (5 Major); after rework ✅ Complete for phases 1, 2, 3, 4, 5, 7, 8 (phase 6 verified by the parent and by external review, not by an RPI validator; phases 9 to 11 pending)

Method and deviations: `/hve-review director-context-picker --mode standard`. Seven `hve-rpi-validator` agents (phases 1, 2, 3, 4, 5, 7, 8) and one `hve-implementation-validator` ran. The quality validator was dispatched in the same batch as the RPI validators instead of after them, to save time against a deadline; this is a deviation from standard mode and changes only timing. Validators read the merged tree at `.claude/worktrees/integration` (commit `af7d928`), before several reworks listed under Parent rulings and resolutions. Phase 6 was NOT validated by an RPI validator, because its search was being reworked at the time (its first delivery was marked Blocked in the changes log). Phases 9, 10 and 11 were not complete at review time. The record-consistency scan of the changes log was done per phase by each validator rather than end to end by the parent, because of the parent's context limit. The parent did not re-run validators after the reworks.

All validation files are in `.claude-hve-tracking/reviews/rpi/2026-10-11/`. Every count below is copied from the named file's `Status:` or `Summary` line. Line citations inside quoted findings refer to the validated tree (`af7d928`) and to the changes log as it stood before the Corrections of 2026-10-11.

## Phase Reviews

### Phase 1: Strict input validation
Source: `director-context-picker-phase-001-validation.md`
Verdict: Pass (0 Critical, 0 Major, 4 Minor)
Coverage: 67% strict (2 of 3 steps Implemented, 1 Deviated); details section 2 rule coverage 15 of 15
Critical and Major findings: none.
Minor (4):
- IV-001: Unrecorded reversal of a recorded plan decision
- IV-002: Phase 1 counts and line citations falsified by the files
- IV-003: Stale location and status statements in the Phase 1 section
- IV-004: Sample-session criterion can go unmeasured silently; wall-clock assertions

### Phase 2: Model and legality core
Source: `director-context-picker-phase-002-validation.md`
Verdict: Pass (0 Critical, 0 Major, 4 Minor)
Coverage: 100% (4 of 4 steps Implemented)
Critical and Major findings: none.
Minor (4; this file gives no titles, so each line is the finding's plan item and subject):
- IV-001: Step 2.3 and the under-60 ms success criterion (timing recorded but not reproducible from the artifact)
- IV-002: Step 2.3, record consistency (28-instance timing figure against 25 instances that build)
- IV-003: Phase 2 record versus plan:212 (files recorded as left uncommitted; no trace to PR #13)
- IV-004: Step 2.2, sample session numbers (18 legal sets, two tied optima and 77 or 79 tokens not pinned)

### Phase 3: Independent legality checker, oracle and generators
Source: `director-context-picker-phase-003-validation.md`
Verdict: Pass (0 Critical, 0 Major, 4 Minor)
Coverage: 100% (5 of 5 plan steps Implemented)
Critical and Major findings: none.
Minor (4; plan item and subject):
- IV-001: Step 3.3, record consistency (`tests/gen.py` line count and citations stale)
- IV-002: Step 3.4 and Step 3.5, record consistency (`tests/test_checker_oracle.py` 560 lines and 45 tests against 618 and 50)
- IV-003: Step 3.3, unrecorded post-landing change (`random_request` raises `ValueError`; PR #15 fixes recorded nowhere)
- IV-004: Step 3.4, traceability (tiny fixtures' tokens and weights have no cited source)

### Phase 4: Packaging and Docker benchmark harness
Source: `director-context-picker-phase-004-validation.md`
Verdict: Fail (0 Critical, 2 Major, 5 Minor)
Coverage: 50% (2 of 4 steps Implemented; 1 Deviated, 1 Partial)

#### IV-001 [MAJOR]
Plan item: Step 4.1 / details :232 ("the script must fail if any `.py` hash differs from `python_sources_after`").
Evidence: the check runs only with `--verify-results` (`tools/build_package.py:120-121`, `:129-130`, `:139`). The invocation details :222 names (`tools/build_package.py --out build/pkg`) packages a stale or absent `benchmark_results.json` with rc=0 (`tests/test_tools.py:137-139` pins this). The plan contains no occurrence of `verify-results`. Nothing downstream closes the gap: `tools/check_results.py` never hashes the `.py` files in `<dir>` (it reads only the results and inputs, `:340-354`) and accepts a results file whose inventory lacks the recorder (`:165-167`); `tools/make_zip.py` checks nothing.
Impact: a final build without the flag ships sources that differ from the recorded run, and every tool exits 0.
Recommendation: verify whenever `benchmark_results.json` is present (pre-run staging builds have none), or write `--verify-results` into the Phase 11 step; have `check_results.py` compare on-disk `.py` hashes with `python_sources_after`.

#### IV-002 [MAJOR]
Plan item: Step 4.3 and the success criterion (plan :77, :82).
Evidence: the pasted run (changes log :170-174) is from the 65-line script. The rework changed the container command to exit with the recorder status and added the outer status handling (`tools/run_recorded.sh:10`, `:57-66`). The only test is a text match (`tests/test_tools.py:181-192`). Parent: not run under Docker since the rework. Reading the script found no defect.
Impact: the Phase 9 recorded run would be the first execution of the delivered script; a failure there would be loud, not silent, but costs time against the deadline.
Recommendation: one stub dry run in a fresh directory; append the command and output to the Phase 4 section.

Minor (5; plan item and subject):
- IV-003: changes-log record consistency (falsified claims, no Correction)
- IV-004: changes-log record consistency (stale counts and line references)
- IV-005: Step 4.1, details :222 (`director_session.json` copied with an existence check only, no hash)
- IV-006: research :107-108 (no tool reads `benchmark_run.log`; `wall_limit_seconds`, `invocation`, `rss_units` not asserted)
- IV-007: Step 4.1, `check_results.py` exit code (`--allow-wrong` returns 0 on integrity failures; booleans accepted as numbers)

### Phase 5: Exact search for 24 or fewer active cards
Source: `director-context-picker-phase-005-validation.md`
Verdict: Pass (0 Critical, 0 Major, 7 Minor)
Coverage: 100% (3 of 3 steps)
Critical and Major findings: none.
Minor (7; plan item and subject):
- IV-001: Step 5.2 / 5.3 record (`tests/test_exact.py` 314 lines and 11 tests against 408 and 15; stale citations)
- IV-002: Step 5.2 record ("no independent optimum check" contradicts the file)
- IV-003: Step 5.2, deadline test (0.07 s limit in the log; test now asserts 0.25 s; loosening unrecorded)
- IV-004: Step 5.1, DD-P5-2 (overshoot "near 1 ms" contradicts the entry's own figures, about 8 ms)
- IV-005: Step 5.1, DD-P5-5 ("weights never negative" left at [MEDIUM], unchecked)
- IV-006: Step 5.2 guard, time margin (Docker worst 1.88 s against the 1.5 s host figure; not recorded)
- IV-007: phase process (`python.md` and `python-tests.md` not read)

### Phase 7: Certificate-profile knapsack and certificate
Source: `director-context-picker-phase-007-validation.md`
Verdict: Pass (0 Critical, 0 Major, 2 Minor)
Coverage: 100% (4 of 4 steps Implemented)
Critical and Major findings: none.
Minor (2; plan item and subject):
- IV-001: Step 7.2 and Step 7.3 evidence citations, record consistency (six citations one line early; 339 lines against 340)
- IV-002: success criterion "finishes in under 1.5 s on the host or returns `None`" (test asserts 10.0 s; loaded-host 2.4 s not recorded)

### Phase 8: CLI, pipeline and corpus regression
Source: `director-context-picker-phase-008-validation.md`
Verdict: Fail (0 Critical, 1 Major, 6 Minor)
Coverage: 89% (8 of 9 steps Implemented, 1 Deviated)

#### IV-001 MAJOR
Plan item: Step 8.6 and the changes-log record.
Evidence: `seat-p8-pipeline-check-results.txt:17,18,20,24,26,32` show utility 120, 223, 72, 136, 128, 72 on 380 to 476 active cards while neighbours score 38079 to 73602 (`:16,:28,:38,:42`). `RESULT: PASS` (`:88`) checks shape, legality and limits, not quality. The report says the cause was not investigated (`seat-p8-pipeline.md:26,37`). The changes log lists only consistency under Issues (changes log:439) and omits this. The table has no `method=` column, so it is not established whether these are search results or the mandatory-closure fallback (`dcp_pipeline.py:82-83,131-133`).
Impact: the contract's main target, 99% of a comparison utility under an all-member gate (`resources/director_context_contract.md:151,157`), may fail on 6 of 15 large instances, and nothing in Phase 8 would show it.
Recommendation: read the recorded stderr `method=` for the six ids; add a dated entry to the Phase 8 log section; hand the ids to `seat-p6-search-r2`; re-measure before Phase 9. The root cause is probably Phase 6's; the missing record is Phase 8's.

Minor (6; plan item and subject):
- IV-002: Step 8.1 (response assembly outside any guard can answer `invalid` for a valid feasible request)
- IV-003: Step 8.3, consistency "asserted" (test only prints; DD-P8-1 not appended to the plan's added requirements)
- IV-004: success criterion, 3.5 s host wall (gate asserts 4.0 s, DD-P8-2)
- IV-005: Step 8.4b (contract-maximum test passes a mandatory-only answer; maxima never run at `--cpus=2`)
- IV-006: A10, not a plan step (24-active evidence is prose only, easy family, self-attested `proven`)
- IV-007: reference-scenario copy test (passes silently when the source is absent; `Tests:` line describes the branch, not the merged tree)

## Quality Findings
Source: `director-context-picker-quality.md`
Verdict: Pass by the gate rule (Critical: 0 | Major: 2 | Minor: 8)
Scope: full-quality (dimensions 1-11); 28 files reviewed. Partial dimensions: 8 (suite not run by the validator, package not built and extracted) and 11 (cited symbols not verified one by one). Not reviewed by instruction: the internal search quality of `dcp_search.py`.

### IV-001 [Error Handling / Security Posture] [MAJOR]
Description: A request inside the 16 MiB raw limit can push peak RSS well over the 256 MiB envelope. `_parse` decodes the whole text with `json` before any structural limit is applied, so a dense array of tiny containers is fully materialized and only then rejected.
Evidence: `dcp_validate.py:108-124` (`raw.decode` then `_DECODER.raw_decode` with no pre-check); `dcp_validate.py:296` catches `MemoryError`, which never fires without an rlimit. Measured here (macOS, python3.11, `/usr/bin/time -l`, input piped to `context_solver.py`):
- `{"cards":[[],[],...]}` at 16 MiB: 448,659,456 bytes max RSS (428 MiB), 2.02 s wall, answer `invalid`
- `{"cards":[{},{},...]}` at 16 MiB: 196,968,448 bytes (188 MiB), 1.78 s
- `{"cards":[1,1,...]}` at 16 MiB: 124,190,720 bytes (118 MiB), 0.93 s
Impact: The answer is correct (`invalid`, exit 0) but the observation breaks the 256 MiB limit, which the contract says is inspected per record (`resources/director_context_contract.md:157`). If a hidden invalid-input group holds one dense near-limit request, that group fails. Wall time of 2.0 s on this host also leaves less margin on the 2-vCPU container. Whether the hidden corpus has such an input is unknown [LOW]; the breach itself is measured [HIGH].
Recommendation: Smallest fix: in `_parse`, before `raw.decode`, reject when `raw.count(b",")` exceeds the largest comma count a valid request can have. Commas can only appear structurally or inside `text` (identifiers cannot contain them). My count: about 64.9k structural plus 500 x 2,048 text characters = about 1.09M, so a cap of 1,100,000 is safe [MEDIUM: recompute the constant from the `_MAX_*` values]. That bounds parsed elements to about 1.1M (roughly 110 MB worst case). Add a CLI test that pipes the 16 MiB `[],` input and asserts `invalid`; assert RSS with `resource.getrusage(RUSAGE_CHILDREN)` where available.

### IV-002 [Test Coverage / Architecture Conformance] [MAJOR]
Description: Several tests read supplied files only from `resources/`, which the package does not contain. `tools/build_package.py:77` copies the three supplied files to the package root, so the test gate run from an extracted package errors.
Evidence:
- `tests/test_exact.py:264` opens `_ROOT/resources/director_session.json` with no root fallback (line 256 of the same file does fall back for `benchmark_inputs.json`)
- `tests/test_model.py:457` same path inside `setUpClass`, so the whole class errors
- `tests/test_tools.py:17` `RESOURCES = REPO / "resources"`, used unguarded at lines 42, 73, 83, 241, 318, 487
- For contrast, the correct pattern is at `tests/test_cli.py:52`, `tests/test_corpus.py:29`, `tests/test_validate.py:738`
Impact: `python3.11 -m unittest discover -s tests` passes in the repo (305 tests, parent's run) and fails after extraction into an empty directory. A reviewer who runs the shipped tests sees errors. Static reading only: I did not build and extract the package to execute this [MEDIUM on exact error count, HIGH on the two direct opens].
Recommendation: One shared helper (for example `tests/paths.py` with `supplied(name)` that tries the root, then `resources/`), used by all seven test modules. In `test_tools.py` resolve `RESOURCES` through the same helper. Then run the gate once from a built package directory.

Minor (8; dimension and subject):
- IV-003 [Security Posture / Overall Quality]: `make_zip.py` excludes fewer names than `build_package.py`, so files created in the package directory after the build are shipped
- IV-004 [DRY Compliance]: constants and helpers duplicated across modules can drift
- IV-005 [API Usage / cross-module seam]: `solve_large` has `max_moves: int = 0`; the fixed interface given for the review is `max_moves=None`
- IV-006 [Error Handling]: two paths answer `invalid` for a request that passed validation
- IV-007 [Overall Quality / deadline arithmetic]: deadlines are offsets from `_T0`, taken after interpreter start, while the docstring calls it "the moment the process started"
- IV-008 [Security Posture / Error Handling]: `tools/run_recorded.sh` robustness gaps (mutable image tag, cleanup under `set -e`, path containing `:`)
- IV-009 [Design Principles]: `LAST_DIAG` is module-level mutable state
- IV-010 [Documentation Integrity]: `README.md` is absent, so `build_package.py --verify-results` cannot pass yet

## Security Findings
Source: `director-context-picker-quality.md`, dimension 9 (ran) and dimension 5 (ran).
- Secret exposure: credential grep over all 28 files for `PRIVATE KEY`, `api_key\s*=`, `password\s*=`, `Bearer `, `-----BEGIN`, `AKIA`/`ASIA`, `AIza`, `ya29.` and service-account JSON: no matches.
- `.gitignore` hygiene: `.gitignore:2-7` lists `.env`, `.env.*`, `*.pem`, `*.key`, `*.p12`, `*.pfx`.
- Committed secrets: `git diff HEAD --name-only` empty; no credential-like tracked files.
- New dependencies: none. Imports are standard library plus local modules only; no manifest, no registry.
- Embedded directives: none seen by the quality validator; the phase 2, 3, 5 and 8 validators also report none in the material they read.
- Findings tagged Security Posture: IV-001 (Major, memory on dense 16 MiB input; resolved, ruling 4), IV-003 (Minor, `make_zip.py` exclusions), IV-008 (Minor, `tools/run_recorded.sh`; the validator found no injection).
- No Critical or Major security finding is open.
- Security was not run by the RPI validators (stated in `director-context-picker-phase-001-validation.md`); the quality validator is the only security pass.

## Record Consistency
- Validators flagged falsified or stale changes-log statements in phases 1, 3, 4, 5 and 7, one figure in phase 2, and a landing-state statement in phases 1 and 2. Phase 8's validator found no internal contradiction and asked for a dated addition to the `Tests:` line.
- After the Corrections of 2026-10-11 in the changes log, every statement the validators flagged in the `### Phase 1:`, `2`, `3`, `4`, `5`, `7` and `8` sections is annotated in place with `(superseded — see Correction 2026-10-11)` and has a dated `Correction (2026-10-11):` entry in a `#### Corrections` subsection of the owning phase. Where the flagged text is pasted command output (phase 4), the annotation is on the lead-in line and the output is left as recorded.
- Phase 6: the `Status:` line is annotated, the rework record ("Rework r2") is appended and a dated Correction states that Blocked describes the first delivery.
- Not annotated: plan:202 ("lone surrogates in `text` are accepted"), which phase 1 IV-001 asked to be annotated. The Phase 1 Correction names it as superseded; the plan file itself is unchanged. Owner: plan.
- Not corrected, because they are not changes-log statements: details:142 ("Always returns a request"), details:226 and details:230 (named in the Phase 3 and Phase 4 Corrections); the code comment at `dcp_exact.py:155-156` that repeats DD-P5-2's claim.
- The scan was per phase, by each validator. No end-to-end scan of the changes log was done, and phases 6, 9, 10 and 11 were not scanned.

## Parent rulings and resolutions
1. Phase 4 IV-001 (Major; source-hash verification only with `--verify-results`): accepted. Resolved by commit `c463fd4` on PR #17 (every build is staged and verified in a temporary directory; final builds require results, log and README) and by procedure: plan step 11.2 runs `tools/build_package.py --verify-results`. Residual: the plain staging build still does not hash sources against results, by design.
2. Phase 4 IV-002 (Major; Docker evidence predated the rework): accepted. Resolved by a run of the reworked `tools/run_recorded.sh` at 14:00 PDT on a clean extraction of the package built from `integration` at `0f4d6cc`: recorder `rc=0`, 28 log lines, `tools/check_results.py` `rc=0`, `RESULT: PASS (0 of 28 records failed, 0 integrity checks failed)`, all 14 integrity checks ok, `quota_vcpus == 2.0`.
3. Phase 8 IV-001 (Major; utilities of 72 to 223 on six large instances): partly contested. Ruling: six public large instances have unit feature weights, so their utility is a card count in the low hundreds by construction and is not comparable with the weighted instances beside them; that part is not a defect. The weak values among them (72 where 120 is reachable) were real and were the phase 6 search gap. Resolved by the search rework (PR #19): the parent's verification at 13:56 PDT ran all 13 large coupled instances with three seeds and two permuted copies each at a 2.0 s deadline; 11 returned one identical value on all five runs, two varied by 6 in 54,795 and 23 in 71,378, and every result passed `dcp_model.is_legal`. Unit-weight values now: 120, 223, 111, 136, 128, 120. Severity kept as Major at validation time; excluded from the open tally as resolved.
4. Quality IV-001 (Major; 16 MiB input of tiny values peaked at 428 MiB in validation): accepted. Resolved by PR #23 (commit `f18f3b9`): byte-count caps reject structurally impossible input before decoding. Measured after: 34 MiB and 0.10 s for the same input; 95 validation tests pass. Not yet measured on Linux.
5. Quality IV-002 (Major; tests read supplied files only from `resources/`): accepted; independently found by the README seat. Resolved by PR #22 (commit `a9bace3`, `tests/test_model.py`, `tests/test_exact.py`) and commit `84ac28d` on PR #17 (`tests/test_tools.py`). Evidence: full regression from a clean extraction of the package at 14:00 PDT: `rc=0`, 337 tests, 0 skipped; from the repository root: `rc=0`, 333 tests, 0 skipped (the counts differ because one branch merged between the two runs).
6. Phase 8 IV-002 and quality IV-006 (Minor; response construction could answer `invalid` for a valid request): raised independently as Critical by the external Codex review of PR #20; fixed in commit `1786157` together with a hard 4.0 s time guard, no-drain handling of oversized stdin and a non-zero exit on stdout failure. Dedup severity: the highest assigned (Critical, external) is noted; resolved.
7. Minor findings that are stale counts, line citations or statements in the changes log are handled by the dated Corrections of 2026-10-11 in the changes log: phase 1 IV-001, IV-002, IV-003; phase 2 IV-002, IV-003; phase 3 IV-001, IV-002, IV-003; phase 4 IV-003, IV-004; phase 5 IV-001, IV-002, IV-003, IV-004, IV-005, IV-006; phase 7 IV-001, IV-002 (18 findings). For phase 5 IV-003 and IV-006 and phase 7 IV-002 the Correction records the fact; the optional code or test change each recommends is not made. Other Minor findings are not fixed and are listed for the owner (20):
   - Phase 1 IV-004 (`director-context-picker-phase-001-validation.md`): sample-session test skips silently when the file is absent; wall-clock assertions.
   - Phase 2 IV-001 (`director-context-picker-phase-002-validation.md`): step 2.3 timing command not recorded verbatim, not reproducible.
   - Phase 2 IV-004 (`director-context-picker-phase-002-validation.md`): 18 legal sets, two tied optima and 77 or 79 tokens not pinned in `tests/test_model.py`.
   - Phase 3 IV-004 (`director-context-picker-phase-003-validation.md`): tiny fixtures' tokens and weights have no cited source.
   - Phase 4 IV-005 (`director-context-picker-phase-004-validation.md`): `director_session.json` has no baseline hash in `tools/build_package.py`.
   - Phase 4 IV-006 (`director-context-picker-phase-004-validation.md`): no tool compares `benchmark_run.log` with the records; `wall_limit_seconds`, `invocation`, `rss_units` not asserted.
   - Phase 4 IV-007 (`director-context-picker-phase-004-validation.md`): `--allow-wrong` returns 0 on integrity failures; numeric fields accept JSON booleans.
   - Phase 5 IV-007 (`director-context-picker-phase-005-validation.md`): `python.md` and `python-tests.md` not read for `dcp_exact.py` and `tests/test_exact.py`.
   - Phase 8 IV-003 (`director-context-picker-phase-008-validation.md`): consistency printed, not asserted; DD-P8-1 not appended to the plan's added requirements.
   - Phase 8 IV-004 (`director-context-picker-phase-008-validation.md`): host wall assertion is 4.0 s against the plan's 3.5 s; not recorded in the plan.
   - Phase 8 IV-005 (`director-context-picker-phase-008-validation.md`): contract-maximum CLI test passes a mandatory-only answer; maxima not timed at `--cpus=2`.
   - Phase 8 IV-006 (`director-context-picker-phase-008-validation.md`): A10 evidence is prose only; no coupled 24-active case through the CLI.
   - Phase 8 IV-007 (`director-context-picker-phase-008-validation.md`): `tests/test_reference_scenarios.py:21-23` passes silently when the source is absent. Its second half (the `Tests:` line) has a dated Correction.
   - Quality IV-003 (`director-context-picker-quality.md`): `make_zip.py` exclusions narrower than `build_package.py`. Commit `aa0dde2` adds `gate.log` and `*.pyc`; not re-validated.
   - Quality IV-004 (`director-context-picker-quality.md`): duplicated baseline hashes and `_utility`.
   - Quality IV-005 (`director-context-picker-quality.md`): `solve_large` `max_moves` default and the `LAST_STATS` and `DEFAULT_SEED` names as interface. The phase 6 rework record states `max_moves` accepts `None` and both `LAST_STATS` keys are kept; not re-validated.
   - Quality IV-007 (`director-context-picker-quality.md`): docstring wording for `_T0`.
   - Quality IV-008 (`director-context-picker-quality.md`): `tools/run_recorded.sh` image by mutable tag, cleanup under `set -e`, path containing `:`.
   - Quality IV-009 (`director-context-picker-quality.md`): `LAST_DIAG` module-level mutable state.
   - Quality IV-010 (`director-context-picker-quality.md`): `README.md` absent at validation time; the README has since landed (changes log Phase 10); the citation re-check the finding asks for is not done here.

## Summary
Raw tally at validation time, summed from the eight files' own counts:

| File | Critical | Major | Minor |
|---|---|---|---|
| `director-context-picker-phase-001-validation.md` | 0 | 0 | 4 |
| `director-context-picker-phase-002-validation.md` | 0 | 0 | 4 |
| `director-context-picker-phase-003-validation.md` | 0 | 0 | 4 |
| `director-context-picker-phase-004-validation.md` | 0 | 2 | 5 |
| `director-context-picker-phase-005-validation.md` | 0 | 0 | 7 |
| `director-context-picker-phase-007-validation.md` | 0 | 0 | 2 |
| `director-context-picker-phase-008-validation.md` | 0 | 1 | 6 |
| `director-context-picker-quality.md` | 0 | 2 | 8 |
| Total | 0 | 5 | 40 |

The raw Minor total counts one issue twice: phase 8 IV-002 and quality IV-006 are the same defect (ruling 6). No validator assigned Critical; the external Codex review of PR #20 graded that defect Critical, and it is fixed.

Open tally after the resolutions above: Critical 0, Major 0, Minor 20. Of the 40 Minor findings, 18 are handled by dated Corrections, 2 are resolved by commit `1786157` and 20 remain open (listed in ruling 7).

Status at validation time: ⚠️ Needs Rework (5 Major)
Status after rework: ✅ Complete for phases 1, 2, 3, 4, 5, 7, 8, with phase 6 verified by the parent and by external review rather than by an RPI validator; phases 9 to 11 pending

Record consistency: after the Corrections of 2026-10-11, every contradiction the validators flagged in the changes log carries an in-place annotation and a dated Correction. One flagged annotation outside the changes log is not made: plan:202 (see Record Consistency).

Limits of this review: validators were not re-run after the reworks, so every resolution above rests on the parent's evidence as stated in each ruling, not on a validator's reading of the reworked code.
