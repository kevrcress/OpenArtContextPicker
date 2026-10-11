# RPI Validation: Director context picker — Phase 1
Date: 2026-10-11
Plan phase: Phase 1: Strict input validation (plan:36-46)
Coverage: 67% strict (2 of 3 steps Implemented, 1 Deviated); details section 2 rule coverage 15 of 15
Status: Pass (0 Critical, 0 Major, 4 Minor)
Scope: Phase 1 only; static read of the merged tree `.claude/worktrees/integration`. No shell: gate results are the parent's evidence (91 tests, rc=0; full suite 305, 0 skipped). Changes log: only `### Phase 1:` (changes:14-51) was read; other sections were touched only by match-only greps (file names, "surrogate", "Correction", "Codex"). Security dimension not run here.

## Plan Item Comparison
| Plan Step | Changes Log Status | Evidence File | Status |
|---|---|---|---|
| Step 1.1: `InvalidRequest`, `validate_request` per details section 2 | Found (changes:27) | `dcp_validate.py:38`, `dcp_validate.py:274` | Deviated: all 15 rules present, plus an unplanned lone-surrogate rejection (IV-001) |
| Step 1.2: tests for every rule | Found (changes:28) | `tests/test_validate.py:107-754` | Implemented: every item of plan:45 has a test; decoder defaults pinned at `tests/test_validate.py:234` |
| Step 1.3: gate with `; echo rc=$?` | Found (changes:29, :47) | parent shell evidence | Implemented: rc=0 (log says 86 tests, tree has 91; IV-002) |

Success criteria (plan:40): gate passes (parent evidence); accept and reject case per rule (table below); sample session and limit-sized request under 100 ms asserted at `tests/test_validate.py:737` and `:746`, sample file present at `resources/director_session.json`, 0 skipped per parent.

## Rule Coverage (details section 2 -> code -> accepting / rejecting test)
| Rule (details line) | `dcp_validate.py` | `tests/test_validate.py` |
|---|---|---|
| Size limit, checked before decode (:54) | :109 | :118 / :124 |
| Strict UTF-8, BOM invalid (:55) | :111-113, :290 | :132 / :128, :137 |
| `raw_decode`, JSON whitespace only, empty input (:56) | :114-121 | :156 / :140, :150, :159 |
| Hooks: duplicate keys, floats, constants (:57) | :42-47, :56-68 | :204 / :173, :177, :182, :209, :225 |
| `type(x) is int`, huge literals (:58) | :50-53, :83-87, :183 | :204 / :214, :230 |
| Top level: object, exactly seven keys (:59) | :117, :261 | :112 / :145, :248, :255 |
| Identifier pattern, separate namespaces (:60) | :33, :71, :181 | :308, :328 / :314, :320, :335 |
| `versions`, `parents`, acyclic (:61) | :127-172 | :348-369, :401, :406 / :373-399, :412 |
| `cards` fields and limits, `text` (:62) | :190-219, :224-226 | :436-512, :551 / same tests, :563 |
| Supersession ancestry; requirement cycles valid (:63) | :227-234 | :514, :517, :539, :544 / :524-537 |
| `features` (:64) | :175-187 | :606-625 |
| `head`, `budget`, `mandatory` (:65) | :265-269 | :421, :627, :635 |
| `contradictions` (:66) | :238-256 | :661, :666 / :672-696 |
| `None` only as `conflict_group` (:67) | :210 plus every type check | :643 |
| Validate before feasibility; ASCII reasons, no echo (:68) | :259-271, imports :9-10 | :98-104, :700 |
Interface (details:46-49): only `InvalidRequest` escapes, `dcp_validate.py:286-299`; tests `:169`, `:187`. `MemoryError` branch (`:296`) has no test (impractical).

## Findings
### IV-001 [MINOR] Unrecorded reversal of a recorded plan decision
Plan item: Step 1.1. Evidence: `dcp_validate.py:35` and `dcp_validate.py:220-221` reject lone surrogates in `text`; plan:202 says "A-15, A-18 and A-19 need no code: lone surrogates in `text` are accepted"; details:62 has no such rule. Changes log Phase 1 (changes:14-47) has no DD- entry and no Correction; "surrogate" and "Codex" match nowhere in the changes log, and plan:202 carries no superseded annotation.
Impact: disk says the opposite of what ships; a later phase (README, review) reading the plan will state the wrong behaviour. The change itself was reviewed in PR #14 (parent evidence), so not graded as a correctness defect.
Recommendation: add `Correction (2026-10-11):` to the Phase 1 section (rework after PR #14 review, files, 5 new tests at `tests/test_validate.py:574-602`, `-0` finding declined per contract line 62 and research A-14) and annotate plan:202 `(superseded — see Correction 2026-10-11)`.

### IV-002 [MINOR] Phase 1 counts and line citations falsified by the files
Plan item: Steps 1.1-1.3 record. Evidence: changes:22 says `dcp_validate.py` is 296 lines, actual 299; changes:23 says 722 lines and 86 test methods, actual 758 lines and 91 methods (`tests/test_validate.py:108-752`); changes:47 says "86 passed" against the parent's 91. Citations are off by +1 or +3: `InvalidRequest` :37 is `dcp_validate.py:38`; `validate_request` :271 is `:274`; :62 is `:63`; :107/:108 are `:108`/`:109`; :126 is `:127`; :189 is `:190`; :235 is `:238`; :295 is `:298`; DD-P1-01 :49 is `:50`; DD-P1-02 :116 is `:117`.
Impact: record only; consistent with the 3 lines added by the IV-001 rework. No Correction annotation, so per CLAUDE.md the log cannot be graded Complete as written.
Recommendation: cover in the same Correction entry (new counts, gate result 91 tests rc=0, line shift).

### IV-003 [MINOR] Stale location and status statements in the Phase 1 section
Plan item: record. Evidence: changes:19 ("Uncommitted in worktree ... the parent commits and merges"), changes:24 and changes:32 ("exists only in the worktree copy ... main checkout's Phase 1 section still reads `Status: Pending`") are falsified: the section is in the main checkout with `Status: Complete` (changes:15) and PR #14 is merged (parent evidence). changes:19 also conflicts with plan:213 (the owner merges PRs).
Impact: record only. Recommendation: annotate the three lines as superseded in the same Correction.

### IV-004 [MINOR] Sample-session criterion can go unmeasured silently; wall-clock assertions
Plan item: success criterion plan:40. Evidence: `tests/test_validate.py:740-741` skips when `director_session.json` is absent (disclosed at changes:36); `tests/test_validate.py:744` and `:750` assert best-of-5 under 0.1 s.
Impact: met in the merged tree (0 skipped). In a clean ZIP extraction without that file the criterion is skipped with rc=0; on a throttled container the timing asserts could fail the regression for a non-functional reason.
Recommendation: confirm the packaged regression's skip count after clean extraction; no code change needed for this phase.

## Unlisted Changes
None. All 28 files on the parent's changed-file list are named somewhere in the changes log (match-only grep over the whole file). Phase 1's own two files are both in its section (changes:22-23).

## Research Coverage
R-07 to R-46 and R-49 to R-51 (structural validity) each map to a test in the table above; A-01 to A-05, A-07 to A-09, A-13 are met. A-14 (`-0` is integer zero, research:129) is met at `dcp_validate.py:53` and `tests/test_validate.py:205`. A-15 is the one divergence (IV-001). R-75 (invalid outranks infeasible) belongs to Phase 8.
Not verifiable without a shell: changes:43-45 corpus measurements (26 valid, 2 invalid, 9.22 ms); `resources/benchmark_inputs.json` was not read, as instructed. Verified statically: no line over 120 characters in either file; no `tests/__init__.py`; imports are `json` and `re` only (`dcp_validate.py:9-10`).
