# Implementation Validation: director-context-picker
Date: 2026-10-11
Scope: full-quality (dimensions 1-11) | Not covered: none skipped; see Coverage Notes for partial ones
Files Reviewed: 28 (read in full: context_solver.py, dcp_pipeline.py, dcp_validate.py, dcp_model.py, dcp_exact.py, dcp_profile.py, tools/*; grep-level: tests/*, dcp_search.py interface only)
Code root: `/Users/kevin/GitHub/OpenArtContextPicker/.claude/worktrees/integration` (paths below are relative to it)

## Summary
Critical: 0 | Major: 2 | Minor: 8

Verdict: Pass by the gate rule (no Critical, 2 Major). Both Majors can fail an all-member group or the
package's own test gate, so fix them before the recorded run.

## Findings

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

### IV-003 [Security Posture / Overall Quality] [MINOR]
Description: `make_zip.py` excludes fewer names than `build_package.py`, so files created in the package directory after the build are shipped.
Evidence: `tools/make_zip.py:17` (`__pycache__`, `.DS_Store`) versus `tools/build_package.py:30` (also `gate.log`, `.git`, `.claude`, `.claude-hve-tracking`, and `.pyc` at line 45).
Impact: Scenario: build, run the test gate inside the package directory (`> gate.log` per the standing rule), then zip. `gate.log` lands in the archive; `verify_results` does not notice because it only hashes `*.py` (`tools/build_package.py:99`).
Recommendation: Import one `EXCLUDED_NAMES` from a single place, or have `make_zip` refuse any file that `build_package.planned_files` would not produce.

### IV-004 [DRY Compliance] [MINOR]
Description: Constants and helpers duplicated across modules can drift.
Evidence: supplied-file SHA-256 baselines in `tools/build_package.py:23-26` and `tools/check_results.py:25-26`; `_utility` in `dcp_pipeline.py:30` and `tools/tune_search.py:29`; bit-walk loops in `dcp_exact.py:17` and `dcp_model.py:170,310,348,359`.
Impact: A baseline changed in one tool only gives a build that passes and a check that fails (or the reverse).
Recommendation: `check_results.py` imports the baseline from `build_package.py` (both ship in `tools/`). Leave the bit loops; they are hot paths.
Note: the second definitions of "active" (`tests/checker.py`, `tests/gen.py:34`, `tests/test_checker_oracle.py:108`) and of the certificate profile (`checker.is_certificate_profile` versus `dcp_profile.py:19`) are deliberate independent re-implementations for judging the solver. No action; `dcp_pipeline` itself has one definition of each (`dcp_model._active_ids`, `dcp_profile.profile_applies`).

### IV-005 [API Usage / cross-module seam] [MINOR]
Description: `solve_large` in the tree has `max_moves: int = 0` with "0 means no limit"; the fixed interface given for this review is `max_moves=None`.
Evidence: `dcp_search.py:38-41`; callers `dcp_pipeline.py:80` (positional `p, deadline` only) and `tools/tune_search.py:34` (`p, deadline, seed`).
Impact: None for the pipeline today; both callers stay valid under either default. `tools/tune_search.py:48,50` and `tests/test_search.py:148` read `dcp_search.LAST_STATS["moves"]` and `["greedy_utility"]`, and `DEFAULT_SEED`; the rework must keep those names or the tool and test break.
Recommendation: Tell the agent reworking `dcp_search.py` that `LAST_STATS` keys and `DEFAULT_SEED` are part of the interface.

### IV-006 [Error Handling] [MINOR]
Description: Two paths answer `invalid` for a request that passed validation.
Evidence: `dcp_pipeline.py:113-116` (unexpected failure in `build_problem`); `dcp_pipeline.py:135-142` are outside any `try`, so a failure there reaches `context_solver.py:43-44` and prints the `invalid` internal-error line.
Impact: Wrong status for a valid request, but only after an internal defect; no traceback reaches stdout and the exit code stays 0 on every path I traced (`context_solver.py:51-56`).
Recommendation: Accept as is; optionally wrap lines 135-142 and fall back to the mandatory mask, which `build_problem` guarantees legal.

### IV-007 [Overall Quality / deadline arithmetic] [MINOR]
Description: Deadlines are offsets from `_T0`, taken after interpreter start, while the module docstring calls it "the moment the process started".
Evidence: `context_solver.py:8`; `dcp_pipeline.py:3-4,21-24`.
Impact: Interpreter start (tens of ms, more on a cold container) is not counted. Worst case is the unproven exact path ending at 3.5 s plus start-up and output, which leaves about 1.4 s. No failing scenario found: max profile instance (500 active, budget 8,192, 1,024 features) measured 0.44 s and 27 MiB with `method=profile proven=True`.
Recommendation: Fix the docstring wording. No code change.

### IV-008 [Security Posture / Error Handling] [MINOR]
Description: `tools/run_recorded.sh` robustness gaps. No injection: every expansion is quoted, the inner command is a constant, and `rm -rf` only reaches `__pycache__` directories under the resolved package directory.
Evidence: `tools/run_recorded.sh:8` image by mutable tag `python:3.11-slim`, not by digest; `:61` `find ... -exec rm -rf {} +` under `set -e`, so on a Linux host root-owned `__pycache__` makes the script exit non-zero after a good run and skips the report at `:63-70`; `:58` `-v "${dir}":/work` mis-parses a path containing `:`.
Impact: Reproducibility of the recorded environment; a false failure on Linux hosts.
Recommendation: Pass `-e PYTHONDONTWRITEBYTECODE=1` only if the recorder's inventory is unaffected (it hashes `*.py` only), or append `|| true` to the cleanup; record the image digest in the run log.

### IV-009 [Design Principles] [MINOR]
Description: `LAST_DIAG` is module-level mutable state used to pass diagnostics from `run` to the CLI.
Evidence: `dcp_pipeline.py:27,97,118,123`; read at `context_solver.py:35`.
Impact: Harmless for a one-shot process; tests that call `run` repeatedly share it.
Recommendation: Leave; a returned tuple would be cleaner if `run` is touched again.

### IV-010 [Documentation Integrity] [MINOR]
Description: `README.md` is absent, so `build_package.py --verify-results` cannot pass yet and nothing documents the layout the tests expect.
Evidence: `tools/build_package.py:33,81-85`.
Impact: Known and in progress (another agent). Listed so the final gate checks it.
Recommendation: When the README lands, re-run the citation check: it must name symbols, not `file:line`.

## Coverage Notes
- 1 Architecture: ran. Layering is clean: `context_solver` -> `dcp_pipeline` -> validate/model/profile/exact/search; no solver module imports `tests/` or `tools/`; `tools/check_results.py:46-54` loads the checker by path and never imports the solver. Finding IV-002.
- 2 Design principles: ran. IV-009.
- 3 DRY: ran with grep. IV-003, IV-004.
- 4 API usage: ran for the seams. `solve_exact(p, deadline, incumbent=)`, `solve_profile(p, deadline)`, `profile_applies(req, p)`, `build_certificate(p, mask)` and `solve_large(p, deadline)` all match their call sites in `dcp_pipeline.py:57-86,145`. IV-005.
- 5 Version consistency: ran. Imports are standard library plus local modules only; no manifest, no new dependency, no registry.
- 6 Refactoring: ran lightly; nothing beyond IV-004.
- 7 Error handling: ran. Every stdout path in `context_solver.py` writes one line and returns 0. IV-001, IV-006.
- 8 Test coverage: partial. Every module has a test file; I did not run the suite (the parent's run: rc=0, 305 tests) and did not build and extract a package. IV-002 is from reading.
- 9 Security: ran. Credential grep over all 28 files for `PRIVATE KEY`, `api_key\s*=`, `password\s*=`, `Bearer `, `-----BEGIN`, `AKIA`/`ASIA`, `AIza`, `ya29.`, service-account JSON: no matches. `.gitignore:2-7` lists `.env`, `.env.*`, `*.pem`, `*.key`, `*.p12`, `*.pfx`. `git diff HEAD --name-only` empty; no credential-like tracked files. No embedded directives seen in the files I read. IV-001, IV-003, IV-008.
- 10 Overall quality: ran. IV-007.
- 11 Documentation: partial. Citation check ran: `docs/research-prompt.md` and `docs/task-brief.md` name the modified files; no bare `file:line` citations in `docs/` or `CLAUDE.md`. I did not extract and verify cited symbols one by one. `README.md` does not exist yet. IV-010.
- Not reviewed by instruction: the internal search quality of `dcp_search.py`. Not reviewed for lack of time: line-by-line reading of `tests/*.py` and whether the exact search can exceed 3.5 s on an adversarial 24-card request.
- Commands I ran wrote nothing in the code root (`PYTHONDONTWRITEBYTECODE=1`, inputs piped on stdin).
