# RPI Validation: Director context picker — Phase 4
Date: 2026-10-11
Plan phase: Packaging and Docker benchmark harness
Coverage: 50% (2 of 4 steps Implemented; 1 Deviated, 1 Partial)
Status: Fail (0 Critical, 2 Major, 5 Minor)

Code read at `.claude/worktrees/integration` (merged state, after rework commit 212e89c per the parent; the commit itself was not inspected, no shell). Shell evidence is the parent's: full suite rc=0 (305 tests), `test_tools.py` 29 tests rc=0, `bash -n tools/run_recorded.sh` rc=0, reworked `check_results.py` exit 1 on a stub run with all integrity checks ok. `resources/benchmark_inputs.json` was not read. Not verifiable here: the executable bit on `tools/run_recorded.sh`.

## Plan Item Comparison

| Plan Step | Changes Log Status | Evidence File | Status |
|---|---|---|---|
| Step 4.1: four tools per details section 9; `build/` in `.gitignore` | Found (changes log :158) | `tools/build_package.py:110`, `tools/run_recorded.sh:20`, `tools/check_results.py:124`, `tools/make_zip.py:33`; `.gitignore:29` already has `build/` (deviation recorded at changes log :155) | Deviated (IV-001, IV-003, IV-005) |
| Step 4.2: `tests/test_tools.py` | Found (:159) | `tests/test_tools.py:77` (byte copies), `:91` (hash refusal on a temp copy), `:208` (archive root, no `__pycache__`) | Implemented |
| Step 4.3: stub dry run under Docker, output pasted | Found (:163-203), pre-rework script only | `tools/run_recorded.sh:10`, `:57-66` changed afterwards | Partial (IV-002) |
| Step 4.4: `resources/` hashes after the dry run | Found (:215-221) | corroborated by `tests/test_tools.py:71-75` passing in the parent's rc=0 suite | Implemented |

Success criterion (plan :77): 28-line log, `quota_vcpus` 2.0, `check_results.py` exit 1 with integrity ok, hashes unchanged. All four are in the changes log (:173-176, :182-188, :218-220) for the pre-rework tools. For the reworked tools only the `check_results.py` half is re-evidenced (parent run); the `run_recorded.sh` half is not (IV-002).

## Details section 9 behaviors in the tools

| Behavior | Evidence | Result |
|---|---|---|
| Package contents; exclusions (`__pycache__`, `.DS_Store`, `.claude-hve-tracking`, `docs/`, `gate.log`) | `tools/build_package.py:27-30`, `:59-78`; `tests/test_tools.py:77-83` | Present |
| Refuse on a `resources/` hash mismatch | `tools/build_package.py:48-56`, `:126-128`; `tests/test_tools.py:91-99` | Present for 2 of 3 copied files (IV-005) |
| Fail when a `.py` differs from `python_sources_after` | `tools/build_package.py:88-107` | Present only behind `--verify-results` (IV-001) |
| Relative paths, `--cpus=2 --network none`, no memory cap, `__pycache__` removed | `tools/run_recorded.sh:10`, `:58-61` | Present; trailing shell differs from the details text (IV-003) |
| Integrity fields | `tools/check_results.py:147-171`, `:351-354` | Present, plus schema, inventories, entrypoint hash |
| Per record: exit code, timeout, parse error, stdout shape, wall, RSS, checker | `tools/check_results.py:106-121`, `:197` | Present; certificate errors now excluded from the verdict (IV-003) |
| p95 nearest rank; max RSS over valid feasible, 250+ active; three repeat pairs | `tools/check_results.py:99-103`, `:226-235`, `:261-264`; `tests/test_tools.py:478-482` | Present |
| Deterministic ZIP, files at the archive root | `tools/make_zip.py:20-46`; `tests/test_tools.py:208-228` | Present |

## Findings

### IV-001 [MAJOR]
Plan item: Step 4.1 / details :232 ("the script must fail if any `.py` hash differs from `python_sources_after`").
Evidence: the check runs only with `--verify-results` (`tools/build_package.py:120-121`, `:129-130`, `:139`). The invocation details :222 names (`tools/build_package.py --out build/pkg`) packages a stale or absent `benchmark_results.json` with rc=0 (`tests/test_tools.py:137-139` pins this). The plan contains no occurrence of `verify-results`. Nothing downstream closes the gap: `tools/check_results.py` never hashes the `.py` files in `<dir>` (it reads only the results and inputs, `:340-354`) and accepts a results file whose inventory lacks the recorder (`:165-167`); `tools/make_zip.py` checks nothing.
Impact: a final build without the flag ships sources that differ from the recorded run, and every tool exits 0.
Recommendation: verify whenever `benchmark_results.json` is present (pre-run staging builds have none), or write `--verify-results` into the Phase 11 step; have `check_results.py` compare on-disk `.py` hashes with `python_sources_after`.

### IV-002 [MAJOR]
Plan item: Step 4.3 and the success criterion (plan :77, :82).
Evidence: the pasted run (changes log :170-174) is from the 65-line script. The rework changed the container command to exit with the recorder status and added the outer status handling (`tools/run_recorded.sh:10`, `:57-66`). The only test is a text match (`tests/test_tools.py:181-192`). Parent: not run under Docker since the rework. Reading the script found no defect.
Impact: the Phase 9 recorded run would be the first execution of the delivered script; a failure there would be loud, not silent, but costs time against the deadline.
Recommendation: one stub dry run in a fresh directory; append the command and output to the Phase 4 section.

### IV-003 [MINOR]
Plan item: changes-log record consistency (falsified claims, no Correction; the only `Correction` in the file is at :73, Phase 1).
Evidence: (a) changes log :231 "Certificate shape errors ... DO fail the record" is false now: `tools/check_results.py:198-200` routes them to an optional section, and details :230 ("exit code 1 when any ... checker verdict fails") is narrowed with no DD entry. (b) :208-210 `--verify-results` gave rc=0 on a source with no `README.md` (:167) and no `benchmark_run.log` (:205); the current tool refuses that (`tools/build_package.py:33`, `:81-85`). (c) :233 "a missing `README.md` is a warning only" holds only without the flag. (d) :184 and :194 quote check names and text that changed (`tools/check_results.py:158`, `:313`). (e) the container command at `tools/run_recorded.sh:10` no longer matches details :226 and no entry records it.
Impact: per CLAUDE.md "Corrections in Tracking Artifacts", the section cannot be graded Complete as written.
Recommendation: annotate each claim in place and append a dated Correction naming commit 212e89c.

### IV-004 [MINOR]
Plan item: changes-log record consistency (stale counts and line references).
Evidence: :150 137 lines (now 155), :151 65 (73), :152 261 (367), :154 and :236 280 lines and 18 tests (500 and 29). Line references moved: `build_package.py:95` to `:110`, `:21` to `:23`; `run_recorded.sh:19` to `:20`; `check_results.py:94` to `:124`, `:22` to `:25`, `:30` to `:37`; `test_tools.py:75`, `:89`, `:152` to `:77`, `:91`, `:208`.
Recommendation: cover in the same Correction; record the 29-test gate with its command and rc.

### IV-005 [MINOR]
Plan item: Step 4.1, details :222 ("any `resources/` hash").
Evidence: `RESOURCE_BASELINE` holds two files (`tools/build_package.py:23-26`); `director_session.json` is copied (`:27`) with an existence check only (`:54-55`), though research :26 gives its hash.
Impact: an altered sample session ships unnoticed (test fixture, not a graded deliverable).
Recommendation: add the third hash.

### IV-006 [MINOR]
Plan item: research :107-108 ("unedited" results and log).
Evidence: no tool reads `benchmark_run.log`; the final build requires only that it exists (`tools/build_package.py:33`, `:90`). `check_results.py` does not assert `wall_limit_seconds`, `invocation` or `rss_units` (`tools/check_results.py:133-136`, `:168`).
Impact: after a Phase 9 rerun, a log left over from the earlier run passes every tool.
Recommendation: compare the 28 log lines (id, exit_code, wall_ms rounded to 3, peak_rss_kib, timed_out) with the records; assert `wall_limit_seconds == 5.0`.

### IV-007 [MINOR]
Plan item: Step 4.1, `check_results.py` exit code.
Evidence: `--allow-wrong` returns 0 on integrity failures as well as wrong answers (`tools/check_results.py:358-362`). `wall_ms`, `peak_rss_kib` and `exit_code` accept JSON booleans (`:108`, `:117-120`). A non-object record raises at `:170` before the guard at `:175` (traceback, non-zero exit, so it fails closed).
Recommendation: never use `--allow-wrong` in a gate, or limit it to record verdicts; type-check with `type(x) in (int, float)`.

## Unlisted Changes
N/A - no changed-file list supplied by parent. The five Phase 4 files the parent named all appear in the Phase 4 section (:150-154).

## Research Coverage
- Recorder command with relative paths, cwd the package directory (research :90): met, `tools/run_recorded.sh:10`, `:58`.
- The recorder validates nothing (research :91): met, independent checker per record, `tools/check_results.py:197`; solver never imported (`:46-54`).
- Output keys to check (research :96): schema, both hashes, inventories, unchanged flag, entrypoint, quota and all record fields asserted; `wall_limit_seconds`, `invocation`, `rss_units` not (IV-006).
- Byte-identical recorder and corpus in the package (research :110-111): met, `tools/build_package.py:126-128`.
- Results and log unedited (research :107-108): results tied to sources only with `--verify-results` (IV-001); log unchecked (IV-006).
