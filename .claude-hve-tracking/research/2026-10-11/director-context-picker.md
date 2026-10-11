# Research: Director context picker (`context_solver.py`)
Date: 2026-10-11
Task slug: director-context-picker
Confidence: HIGH overall (MEDIUM where marked)
Method: 3 `hve-researcher` subagents (themes A contract, B recorder, C corpus), `--mode standard`, cap 3, started 12:33 PDT, consolidated 12:41 PDT. Parent shell, all read-only: `find`/`wc`/`shasum -a 256` over `resources/`; three `python3.11 -I -c` census one-liners over `resources/benchmark_inputs.json` (shape sketch, per-instance census, active-card/closure/profile/repeat census with a canonical dump of the seven tiny instances); one `grep -c` plus `python3.11 -I -c` scan for `NaN`/`Infinity`/float notation/duplicate keys/identifier pattern; `docker run --rm --cpus=2 --network none python:3.11-slim` printing `python -V`, `/sys/fs/cgroup/cpu.max`, `nproc`, `uname`; `docker image inspect`. Nothing under `resources/` was executed. No web research. Re-checks of negative claims: "no expected outputs" (shape sketch: instances carry only `id` and `request`), "no float/NaN in corpus" (scan), "census2 absent" (it was mid-write when theme C read; its content is consolidated here by the parent).

Agent types: all three were roster `hve-researcher`. No non-roster agent was dispatched in this phase.

Embedded-directive check: none of the three researchers, nor the parent, found text in `resources/` that addresses an agent, claims authority or changes scope. Imperatives there are assignment requirements on the implementer.

## Summary

The problem is budgeted weighted maximum coverage under requirement closures, at-most-one-per-group, an arbitrary conflict graph and forced mandatory cards, after a visibility and supersession filter. The contract demands exact answers at 24 or fewer active cards and 99% of a hidden feasible comparison above that, with every quality group all-or-nothing, so validation and legality outrank utility. The public corpus has 28 requests and no expected outputs: two must answer `invalid`, two `infeasible`, and 13 are large coupled instances where six have unit weights, which makes the 99% bar tolerate a deficit of at most a few cards. The recorder validates nothing, writes its output only at the very end, and hashes every `.py` beside the solver.

## Key Findings

### Integrity baseline

Measured 12:23 PDT on commit `68965ab`; `resources/task.md` was added later by the owner in `5680160` and is not a supplied resource.

| File | Bytes | SHA-256 |
|---|---|---|
| resources/benchmark_inputs.json | 8377534 | 164ea460ed919a4e5e365c5357b9d53606f8f5fb53df8c238664c8117eae541c |
| resources/benchmark_runner.py | 6559 | 87694477eca9636ed78766d4473821befb9d388bf2444b2e1b5310f5e6ca5943 |
| resources/director_context_contract.md | 12831 | 10267a9c8acb1a1753f38e552c72958623abceaeb8524916e2811874060928ed |
| resources/director_session.json | 2324 | 532851d06162a80706a110fdb3cc2aed278c42637daf3eb2e744e29e62bb0b3a |
| resources/director_usage_notes.md | 1990 | 3f3d658e0ae39febf48096e641336b5b075add22ef0d69dfd91fdca0304c34ef |

These match docs/orchestrator-notes.md "Integrity baseline" [HIGH]. Resource mapping: sample session = director_session.json; product notes = director_usage_notes.md; technical contract = director_context_contract.md; test inputs = benchmark_inputs.json; recording tool = benchmark_runner.py. No file fits none.

### Measurement environment (parent check, 12:36 PDT)

- `docker run --rm --cpus=2 --network none python:3.11-slim`: Python 3.11.17, `Linux 6.12.54-linuxkit aarch64`, `/sys/fs/cgroup/cpu.max` = `200000 100000`, `nproc` 8, affinity 8 CPUs, `memory.max` = `max` [HIGH]. The recorder's `cpu_capacity` will therefore record `quota_vcpus` 2.0 with 8 logical CPUs visible (resources/benchmark_runner.py:44-56).
- Image `python@sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce`, arm64. Disclose arm64 in the README.
- A bare interpreter in that container reports `ru_maxrss` 7864 KiB, so the interpreter floor is about 8 MiB [HIGH for this image]. Whether the recorder's meter adds a higher floor to `peak_rss_kib` is unverified [LOW]; measure with the real solver.

### Problem classification

- Maximize the summed weight of the union of covered features (resources/director_context_contract.md:105) subject to: every selected card active and visible (:94), every mandatory card selected (:95), full transitive `requires` closure selected, cycles together (:96), at most one card per non-null group (:97), no contradiction pair with both ends selected (:98), token sum at most budget (:99) [HIGH].
- Generalizes 0/1 knapsack, weighted max coverage and max-weight independent set. NP-hard; the contract promises no topology (:149) [HIGH].
- Active = visible and not superseded, directly or through a chain, by a visible card (:84). Because supersession must come from a strict descendant version (:64), every card under a visible superseder is itself visible, so "active" reduces to "visible and not reachable through `supersedes` from any visible card" [MEDIUM, reasoning from :64 and :82-84].
- The active-card count for quality scopes is taken before removing cards with unusable closures (:88) [HIGH].
- Standard reductions the clauses permit: a closure is unusable if it contains an inactive or invisible card (:86), a contradiction pair (:78), two cards of one group (:97, ambiguity A-12), or costs more than the budget; the mandatory closure is fixed first, and if it is illegal the answer is `infeasible`, otherwise it is itself a legal answer (:101) [HIGH].
- Sample session (resources/director_session.json): 7 active cards, 18 legal sets at budget 100, best utility 61 with two tied optima (portrait, sleeve_detail, closeup plus moon or neon; 77 or 79 tokens). The superseding card `coat` is in neither optimum, and `amber_arrival` is active but unselectable because its closure costs 102 [HIGH, hand walk in the theme C artifact]. A "newest revision wins" rule would score 58.

### Corpus (parent census; files outside the repo, values reproduced here)

28 requests, schema `openart-context-inputs/2`, no expected outputs. No `NaN`, `Infinity`, float notation, booleans, non-ASCII bytes, duplicate keys or bad identifiers anywhere in the corpus file [HIGH, scan]. Columns: active cards / cards / budget / pairs with both ends active / features covered by more than one active card / max closure size.

| Class | Instance | Active | Cards | Budget | Active pairs | Shared feats | Max closure | Note |
|---|---|---|---|---|---|---|---|---|
| Tiny | i_353b0868e8bfb0bb1c | 3 | 3 | 100 | 2 | 0 | 1 | pairs (a,b),(b,c): non-transitivity; best is {a,c} = 60 |
| Tiny | i_93a288225d57a93686 | 3 | 3 | 100 | - | 0 | 1 | pair `["a","a"]`: **must be `invalid`** (:74) |
| Tiny | i_57be790be38419e246 | 3 | 3 | 100 | - | 0 | 1 | pair `["a","b","c"]`: **must be `invalid`** (:74) |
| Tiny | i_5568451c1df999c2c4 | 3 | 3 | 100 | 1 | 0 | 1 | a,b share group `g`, redundant pair (b,a); best {b,c} = 70 |
| Tiny | i_f4bba5cb9d71569f25 | 2 | 3 | 100 | 0 | 0 | 1 | head `left`; card a on `right` is invisible; mandatory b,c; pair (a,b) inert; answer {b,c} = 70 |
| Tiny | i_6bf2ce5fc66d4bad9e | 3 | 3 | 100 | 1 | 0 | 2 | a requires b, b requires a, pair (a,b), mandatory a: **must be `infeasible`** (:78) |
| Tiny | i_354f04e366ba47a0e5 | 3 | 3 | 100 | 1 | 0 | 3 | a→b→c, pair (a,c), mandatory a: **must be `infeasible`** (:78) |
| Small | i_658192e99b3806aff2 | 12 | 12 | 55 | 4 | 6 | 2 | exactness range |
| Small | i_299ba50f55c486ec71 | 16 | 16 | 76 | 10 | 12 | 3 | exactness range |
| Small | i_6421fda8c234f4ca23 | 18 | 18 | 96 | 6 | 9 | 2 | exactness range |
| Mid | i_9cf7bcb5fe8c0fdac3 | 36 | 36 | 185 | 12 | 18 | 2 | 99% range (A-10) |
| Mid | i_4f87def68141976d87 | 48 | 48 | 217 | 16 | 24 | 2 | 99% range (A-10) |
| Mid | i_3fa5a35f7c751fc671 | 64 | 64 | 296 | 40 | 48 | 3 | 99% range (A-10) |
| Large coupled, weighted | i_d377627acc7b53786a | 476 | 488 | 1986 | 3248 | 151 | 4 | repeat of i_b05b69c48293a3d4b4 (signature) |
| Large coupled, weighted | i_b05b69c48293a3d4b4 | 476 | 488 | 1986 | 3248 | 151 | 4 | |
| Large coupled, weighted | i_8d29a9554dd222d976 | 476 | 488 | 1612 | 6496 | 154 | 4 | |
| Large coupled, unit | i_6f0cb82b21cc17afba | 380 | 392 | 1634 | 4048 | 122 | 4 | unit weights with overlapping covers (up to 6 per card) |
| Large coupled, weighted | i_97504cfbf824b0eeee | 380 | 392 | 1337 | 4048 | 122 | 4 | |
| Large coupled, weighted | i_27d35bf2cd22d3769a | 332 | 344 | 1433 | 2880 | 106 | 4 | repeat of i_dfcebb3746dc9feecb (signature) |
| Large coupled, weighted | i_dfcebb3746dc9feecb | 332 | 344 | 1433 | 2880 | 106 | 4 | |
| Large coupled, weighted | i_a7373a7648d6ddce67 | 284 | 296 | 1162 | 1904 | 73 | 4 | |
| Large coupled, unit | i_613d784770e53c543d | 428 | 440 | 1749 | 4992 | 0 | 4 | repeat of i_91a2e8f7679a6871f4 (signature) |
| Large coupled, unit | i_91a2e8f7679a6871f4 | 428 | 440 | 1749 | 4992 | 0 | 4 | |
| Large coupled, unit | i_5fccaf00f31313dcfc | 428 | 440 | 1458 | 4992 | 0 | 4 | same structure, smaller budget |
| Large coupled, unit | i_d755f5d407b0d86c60 | 476 | 488 | 1899 | 6496 | 0 | 4 | |
| Large coupled, unit | i_3b971612ce637e324b | 476 | 488 | 1976 | 7424 | 0 | 4 | densest pairs |
| Large unconstrained | i_cf46e9e6258788de2a | 320 | 320 | 2571 | 0 | 0 | 1 | **certificate profile**; tokens 1..32, weights 4..930 |
| Large unconstrained | i_9e24f6f61fea4413ac | 256 | 256 | 93 | 0 | 0 | 1 | **certificate profile**; all tokens 1, weights 100..994 |

- Class counts by active cards are 7 tiny, 3 small, 3 mid, 13 large coupled, 2 large unconstrained. docs/orchestrator-notes.md says 9 tiny and 11 large coupled; the census does not support that split [HIGH]. No 5-version instance has a small active count.
- Six large coupled instances have unit weights (census1 weight column 1..1); one of them, i_6f0cb82b21cc17afba, also has overlapping coverage. They are: i_613d…, i_6f0c…, i_5fcc…, i_d755…, i_3b97…, i_91a2… [HIGH from census1 weight column]. On unit weights, `100*utility >= 99*comparison` allows a deficit of at most `floor(comparison/100)` features.
- In every large coupled instance: 5 versions, 480 or fewer visible cards, 4 cards deactivated by supersession, 8 cards invisible, exactly 1 mandatory card whose closure costs 4 to 7 tokens, 13 to 16 groups of exactly 2 active cards each, no active card with an unusable closure, closure size at most 4, budget 25 to 32 percent of the active token sum [HIGH].
- Efficiency workload (valid feasible, at least 250 active): 15 public instances. Nearest-rank p95 with n = 15 is the slowest instance (:153) [HIGH arithmetic].
- Three candidate equivalent-repeat pairs by structural signature (not proof of equivalence) [MEDIUM]. Two tiny pairs share a signature only because they differ in the pair contents.
- The public corpus has no instance with 19 to 24 active cards, none between 65 and 249, no supersession at exactness sizes, and never reaches contract maxima (budget 2571 of 8192, tokens 40 of 512, covers 6 of 64, versions 5 of 96) [HIGH]. Hidden grading can; own tests must cover these.

### Recorder (resources/benchmark_runner.py)

- Command, cwd = clean extraction directory, relative paths: `python benchmark_runner.py --solution context_solver.py --inputs benchmark_inputs.json --output benchmark_results.json > benchmark_run.log 2>&1; echo rc=$?` (:85-89, :133) [HIGH]. `--timeout` defaults to 5.0 and is recorded as `wall_limit_seconds`.
- It validates nothing: no legality check, no utility recomputation, exit 0 whatever the solver did (:117-122, :134) [HIGH]. `rc=0` proves only that it finished.
- The output file is written once at the end (:134). An uncaught raise leaves no file. Abort paths: meter non-zero (:113-114), meter over timeout+10 s (:112), a `.py` symlink resolving outside the folder (:35-36), a non-finite float in a parsed response at final serialization (:134, MEDIUM) [HIGH otherwise].
- Solver is launched as `[sys.executable, <absolute solver path>]`, cwd and env inherited, no `-B`; stdin is the canonical sorted compact UTF-8 request plus one newline; on timeout the process group gets SIGKILL (:21, :65-73, :107) [HIGH]. `__pycache__` will be written beside the sources; the inventory skips it (:30-33).
- Wall time is `perf_counter` around `Popen`..`communicate`, including interpreter startup; RSS is `RUSAGE_CHILDREN.ru_maxrss` from a fresh meter process per instance, KiB on Linux (:64, :74-77) [HIGH]. Thresholds in recorded units: 262144 and 65536.
- Source inventory: every `*.py` under the solver's folder, recursive, before and after; `python_sources_unchanged` is recorded, not enforced (:30-33, :126-129) [HIGH]. Tests and the recorder itself are hashed too.
- Output keys to check after the run: `schema`, `inputs_sha256`, `python_sources_before`, `python_sources_after`, `python_sources_unchanged`, `runner_sha256`, `entrypoint_sha256`, `environment.{python,executable,platform,logical_cpus,cpu_capacity.{logical_cpus,affinity_cpus,cgroup_cpu_max,quota_vcpus},rss_units,wall_limit_seconds,invocation}`, `instances[].{stdout,stderr,exit_code,wall_ms,peak_rss_kib,timed_out,id,input_sha256,response,response_parse_error}` (:78-79, :116-133) [HIGH].
- Console: one JSON line per instance and nothing else; `benchmark_run.log` is the operator's redirect (:124-125) [HIGH].
- The recorder does not store the request, only `input_sha256`; recomputing utility from `benchmark_results.json` needs the corpus file [HIGH].

### Deliverable checklist

| Item at ZIP root | Produced by | Source |
|---|---|---|
| `director-context.zip` (archive name) | packaging step | docs/task-brief.md:20 |
| `context_solver.py` | implementation | docs/task-brief.md:27 |
| supporting local modules and tests | implementation | docs/task-brief.md:22 |
| `benchmark_results.json` | recorder `--output`, unedited | docs/task-brief.md:28; resources/benchmark_runner.py:134 |
| `benchmark_run.log` | redirect of recorder stdout and stderr, unedited | docs/task-brief.md:29; resources/benchmark_runner.py:124-125 |
| `README.md` | authored | docs/task-brief.md:30 |
| `benchmark_runner.py`, byte-identical | copy of resources/benchmark_runner.py | resources/benchmark_runner.py:3-4; resources/director_context_contract.md:155 |
| `benchmark_inputs.json` | not named in the brief; needed for any clean-extraction rerun and for recomputing utility | docs/task-brief.md:25-30 (absent) — plan decision |

README sections required (docs/task-brief.md:30): clean-extraction commands; runnable local regression command; method and limitations; measurement environment; operational note. From resources/director_usage_notes.md the operational note must cover handling of bad upstream metadata, a safe fallback, and the limits of the objective (model obedience, rendering overhead, semantic nuance, output continuity, production drift, an extractor that omitted a real conflict) (:7, :9), make no production claims (:11), treat the upstream extractor, weights and tokenizer as assessment assumptions (:5), and separate measurements from estimates (:11).

### Ambiguities and their safest reading (theme A, A-01 to A-20; the ones that change code)

- A-01 empty or whitespace-only stdin: `invalid`, exit 0 [MEDIUM].
- A-02 top-level array or scalar: `invalid` [HIGH].
- A-03 trailing content: trailing JSON whitespace accepted, any other byte `invalid` [MEDIUM].
- A-04 UTF-8 BOM: `invalid`; decode with strict `utf-8` and never hand raw bytes to `json.loads` (it auto-detects UTF-16/32 and BOM) [LOW on the reading, HIGH on the consequence].
- A-05 deep nesting: `invalid`; catch `RecursionError` [MEDIUM].
- A-06 mandatory card inactive or invisible, or its closure reaching one: `infeasible`, not `invalid` [HIGH].
- A-07 `text` length counts code points [MEDIUM].
- A-08 duplicate entries in `mandatory`: `invalid` [HIGH]. A-09 unknown feature in `covers`: `invalid` [HIGH].
- A-10 the 99% bar covers every assessed request above 24 active cards, not only 250 to 500 (:151). This differs from docs/orchestrator-notes.md "names no target for this range" [MEDIUM].
- A-11 supersession ancestry is checked on the whole version graph, independent of `head` [MEDIUM].
- A-12 two cards of one group inside one closure: closure unusable, request valid [MEDIUM].
- A-13 all structural validation completes before any feasibility test (:122) [HIGH].
- A-14 `-0` is integer zero; integer literals over 4,300 digits raise `ValueError` in Python 3.11 and must map to `invalid` [LOW].
- A-16 for a validated feasible request the fallback on any internal error or time shortage is the mandatory closure as `ok`; never `invalid` or `infeasible` for a request that is neither [MEDIUM].
- A-17 a certificate-profile request may still carry `mandatory` and `supersedes`; the certificate's card sum runs over active cards only (:136) [MEDIUM]. Neither public profile instance has mandatory cards or supersession (census).
- A-20 exactly 16,777,216 bytes is allowed; the size check precedes decoding [HIGH].

Python 3.11 parser defaults that contradict the contract [MEDIUM, from library knowledge; verify in the implement phase]: `True` passes `isinstance(x, int)`; `NaN`/`Infinity` accepted; duplicate keys keep the last value; bytes input auto-decoded; `\w` and `str.isalnum` accept non-ASCII; `$` matches before a trailing newline (use `fullmatch`).

### Contradictions between sources

- Brief vs recorder: the brief gives `benchmark_results.json` and `benchmark_run.log` the same description (docs/task-brief.md:28-29); the recorder writes only `--output` (resources/benchmark_runner.py:134) and the log is the console capture. Settled [HIGH].
- Brief vs contract: the brief lists "diagnostics" among recorded values (docs/task-brief.md:28); the contract defines no diagnostics field and routes diagnostics to stderr (:5). Reconciled by the recorder storing raw `stderr` per instance [HIGH].
- Notes vs contract: docs/orchestrator-notes.md says the contract names no target between 25 and 249 active cards; contract :151 words the 99% target for all "larger assessed requests" (A-10) [MEDIUM]. Plan to the stricter reading.
- Notes vs census: 9 tiny / 11 large coupled in the notes; 7 / 13 by measured active count [HIGH].
- Product notes vs contract: no contradiction; the notes add README content (see Deliverable checklist) [HIGH].
- Recorder vs contract on the five-second limit: `wall_ms` starts before `Popen`, the timeout starts at `communicate`, so a record can show `wall_ms` just over 5000 with `timed_out` false (resources/benchmark_runner.py:64, :69); the contract judges observed limits from recorded data (:157). Stay far inside 5 s [HIGH].

### Certificate profile

Under the profile (:143) the formula at :134-139 minimizes to `U(p) = budget*p + sum over active cards of max(0, s*value_c - p*tokens_c)` with `z[f] = features[f]*s`, which is the Lagrangian dual of a 0/1 knapsack; its best price is the fractional-greedy break item's value/tokens ratio, representable exactly as `s = tokens_break`, `p = value_break` [HIGH]. The gap to the integral optimum is below one break item's value. i_9e24f6f61fea4413ac (all tokens 1) has zero gap; i_cf46e9e6258788de2a has an absolute gap below 930 [MEDIUM]. The 5% test is against achieved utility, so the selection on the profile should be the exact knapsack optimum: 320 × 2571 = 0.8M DP cells here, 500 × 8192 = 4.1M at contract maxima.

### Requirements matrix

Theme A's full matrix (R-01 to R-95, each MUST row with a testable assertion) is reproduced below from the subagent artifact so it survives in the committed tree.

Level key: MUST = core, fails a gate if missed. OPTIONAL = optional capability the plan accepts or declines. SHOULD = stated guidance without a direct gate.

#### Process boundary

| ID | Level | Requirement | Source | Testable assertion |
|---|---|---|---|---|
| R-01 | MUST | Entry point is `python context_solver.py`; reads one request from stdin | contract:5 | `python3.11 context_solver.py < req.json` returns a response |
| R-02 | MUST | stdout is exactly one UTF-8 JSON object followed by a newline | contract:5 | stdout ends with `\n`; `json.loads(stdout)` is a dict; no other non-whitespace bytes |
| R-03 | MUST | Exit 0 for every well-formed response, including `invalid` and `infeasible` | contract:5 | Return code is 0 for one request of each status |
| R-04 | MUST | Diagnostics go to stderr only; no progress text or second JSON object on stdout | contract:5 | With diagnostics enabled, stdout still parses as exactly one object |
| R-05 | MUST | Works from an arbitrary writable cwd after clean extraction; no persistent state | contract:5 | Run from an empty temp dir via a path to the script; identical response; no file created in cwd |
| R-06 | MUST | Identifiers, array order, pair orientation, paths and benchmark IDs carry no semantic priority | contract:7 | Shuffle arrays, rename IDs, flip pairs: same status; legal result; same utility when active count <= 24 |

#### Input: parsing and structure

| ID | Level | Requirement | Source | Testable assertion |
|---|---|---|---|---|
| R-07 | MUST | Top level has exactly seven keys, all required: `versions`, `cards`, `features`, `head`, `budget`, `mandatory`, `contradictions` | contract:11, :40 | Removing any one key gives `invalid`; adding key `x` gives `invalid` |
| R-08 | MUST | Raw request is at most 16 MiB of bytes, whitespace included | contract:46 | A valid request padded with spaces to 16,777,216 bytes is not rejected for size; 16,777,217 bytes gives `invalid` |
| R-09 | MUST | Input that is not valid UTF-8 is invalid | contract:5, :46 | A request containing byte `0xFF` gives `invalid`, exit 0 |
| R-10 | MUST | Top-level value must be a JSON object | contract:46, :62 | `[]`, `"x"`, `1`, `null` each give `invalid` |
| R-11 | MUST | Exactly one JSON object; trailing non-whitespace is invalid [MEDIUM, inferred] | contract:5, :46 | `{...}{}` and `{...} x` give `invalid`; `{...}\n` is accepted |
| R-12 | MUST | Duplicate object keys are invalid at every level | contract:40 | A repeated key at top level, in a version, in a card and in `features` each gives `invalid`, even with equal values |
| R-13 | MUST | Unknown keys are invalid, including inside version and card objects | contract:40 | Extra key in the top level, a version, a card each gives `invalid` |
| R-14 | MUST | Identifier: ASCII, 1-64 chars, only letters, digits, `.`, `_`, `:`, `-`; applies to version, card, feature and conflict-group IDs | contract:40 | `""`, 65 chars, `"a b"`, `"é"`, `"a/b"`, `"a\n"` each give `invalid`; a 64-char legal ID is accepted |
| R-15 | MUST | Version, card, feature and conflict-group IDs are separate namespaces | contract:40 | A request using `x` as a version, card, feature and group ID is valid |
| R-16 | MUST | Integer fields need integer notation with no fraction or exponent | contract:62 | `"budget": 1.0`, `"tokens": 1e2`, a weight of `5.0` each give `invalid` |
| R-17 | MUST | Booleans are not integers | contract:62 | `"budget": true`, `"tokens": false`, weight `true` each give `invalid` |
| R-18 | MUST | Non-finite numbers are invalid | contract:62 | `NaN`, `Infinity`, `-Infinity` anywhere give `invalid` |
| R-19 | MUST | Null is permitted only as `conflict_group` | contract:62 | `"text": null`, `"budget": null`, `"mandatory": null`, a null array entry each give `invalid` |
| R-20 | MUST | Every array and object has its stated type | contract:62 | `"cards": {}`, `"features": []`, `"supersedes": "c1"`, a card that is a string each give `invalid` |
| R-21 | MUST | Input arrays need not be topologically sorted | contract:62 | Child version listed before its parent, and a card referencing a later-listed card, are valid |

#### Input: the "Types and limits" table, row by row

| ID | Level | Requirement | Source | Testable assertion |
|---|---|---|---|---|
| R-22 | MUST | `versions`: 1-96 objects, each with exactly `id` and `parents`; unique IDs | contract:47 | `[]` invalid; 97 invalid; 96 valid; two equal IDs invalid; version without `parents` invalid |
| R-23 | MUST | `parents`: 0-8 distinct existing version IDs | contract:48 | 9 parents invalid; repeated parent invalid; unknown parent invalid; 8 valid |
| R-24 | MUST | Version graph is acyclic | contract:48 | `v0 -> v1 -> v0` invalid; a self-parent invalid |
| R-25 | MUST | `cards`: 0-500 card objects; unique card IDs | contract:49 | 501 invalid; 500 valid; `[]` valid; two equal IDs invalid |
| R-26 | MUST | Card has required keys `id`, `version`, `supersedes`, `requires`, `conflict_group`, `tokens`, `covers`; `text` optional | contract:25-38 | Removing each required key in turn gives `invalid`; removing `text` is valid |
| R-27 | MUST | `version`: an existing version ID | contract:50 | Unknown version ID gives `invalid` |
| R-28 | MUST | `supersedes`: array of 0-8 distinct existing card IDs | contract:51 | 9 entries, a repeat, an unknown ID each give `invalid` |
| R-29 | MUST | `requires`: array of 0-8 distinct existing card IDs | contract:51 | 9 entries, a repeat, an unknown ID each give `invalid` |
| R-30 | MUST | `conflict_group`: null or an identifier | contract:52 | `""`, `5`, a 65-char string each give `invalid`; `null` valid; key absent invalid |
| R-31 | MUST | `tokens`: integer 1-512 | contract:53 | 0, 513, -1 invalid; 1 and 512 valid |
| R-32 | MUST | `covers`: 0-64 distinct existing feature IDs | contract:54 | 65 entries, a repeat, an ID absent from `features` each give `invalid` |
| R-33 | MUST | `text`: optional string of at most 2,048 Unicode characters; empty allowed | contract:55 | 2,049 chars invalid; 2,048 valid; `""` valid; a number invalid |
| R-34 | MUST | `text` has no effect on selection or objective; do not retokenize | contract:62 | Changing or removing every `text` leaves status and utility unchanged |
| R-35 | MUST | `features`: object with 0-1,024 feature IDs, each an integer weight 1-1,000 | contract:56 | 1,025 keys invalid; weight 0 or 1,001 invalid; `{}` valid |
| R-36 | MUST | `head`: an existing version ID | contract:57 | Unknown head gives `invalid`; non-string head gives `invalid` |
| R-37 | MUST | `budget`: integer 0-8,192 | contract:58 | -1 and 8,193 invalid; 0 and 8,192 valid |
| R-38 | MUST | `mandatory`: array of distinct existing card IDs; empty allowed | contract:59, :62 | A repeated ID invalid; an unknown ID invalid; `[]` valid |
| R-39 | MUST | `contradictions`: 0-10,000 distinct unordered pairs of existing card IDs | contract:60 | 10,001 pairs invalid; 10,000 valid; `[]` valid |

#### Requirements and supersession

| ID | Level | Requirement | Source | Testable assertion |
|---|---|---|---|---|
| R-40 | MUST | `requires` may form cycles, including a self-requirement; the whole closure is selected together | contract:64 | A card requiring itself is valid and selectable; a 2-cycle is selected both or neither |
| R-41 | MUST | A card cannot supersede itself | contract:64 | `"supersedes": [own id]` gives `invalid` |
| R-42 | MUST | Supersession is valid only when the older card's version is a strict ancestor of the superseder's version | contract:64 | Same-version supersession invalid; sibling-branch supersession invalid; descendant-superseding-ancestor invalid in the reverse direction; parent-to-child valid |
| R-43 | MUST | Array position is not ancestry | contract:64 | Card listed later but in an unrelated version superseding an earlier-listed card gives `invalid` |

#### Pairwise contradictions

| ID | Level | Requirement | Source | Testable assertion |
|---|---|---|---|---|
| R-44 | MUST | Each pair is a two-element array of existing card IDs; wrong length, non-array pair or unknown endpoint is invalid | contract:68, :74 | `["a"]`, `["a","b","c"]`, `"a,b"`, `["a","nope"]` each give `invalid` |
| R-45 | MUST | A self-pair is invalid | contract:74 | `["a","a"]` gives `invalid` |
| R-46 | MUST | A pair given in both orientations, or repeated in either, is a duplicate and invalid | contract:74 | `[["a","b"],["b","a"]]` invalid; `[["a","b"],["a","b"]]` invalid |
| R-47 | MUST | A pair forbids selecting both endpoints; the relation is symmetric | contract:74, :98 | With pair `(a,b)`, no `ok` response contains both |
| R-48 | MUST | Contradictions are not transitive | contract:76 | With pairs `(a,b)` and `(b,c)` only, `a` and `c` may be selected together and are when that is optimal |
| R-49 | MUST | Pairs may sit inside one group, across groups, or on null-group cards; a redundant in-group pair is valid | contract:76 | Pair between two cards of the same `conflict_group` is accepted as valid |
| R-50 | MUST | Pairs naming inactive or invisible cards are structurally valid, bind only those exact endpoints, and never transfer to a successor | contract:78 | `new` supersedes `old`; pair `(old,x)`: request valid, `new` and `x` selectable together |
| R-51 | MUST | A pair inside a requirement closure makes that closure unusable; the request stays valid | contract:78 | `a` requires `b`, pair `(a,b)`, no mandatory: status `ok`, `a` not selected |
| R-52 | MUST | A pair inside the mandatory closure gives `infeasible` | contract:78 | Mandatory `a`, `a` requires `b`, pair `(a,b)`: status `infeasible` |

#### Visibility and revisions

| ID | Level | Requirement | Source | Testable assertion |
|---|---|---|---|---|
| R-53 | MUST | A version is visible when it is `head` or a transitive ancestor of `head`; a card is visible when its version is | contract:82 | A card on a sibling branch or a descendant of `head` never appears in `selected` |
| R-54 | MUST | A visible card is active when no other visible card supersedes it, directly or through a chain | contract:84 | Visible chain `c3 > c2 > c1`: only `c3` is selectable |
| R-55 | MUST | A visible superseder deactivates predecessors even if it is itself superseded | contract:84 | In the chain above `c2` still deactivates `c1`; `c1` never selected |
| R-56 | MUST | An invisible card never suppresses a visible card | contract:84 | Superseder on a branch not visible from `head`: the older card is active and selectable |
| R-57 | MUST | A requirement on an inactive or invisible card is not redirected; the dependent is unselectable | contract:86 | `d` requires `old`, `new` supersedes `old`: `d` is never selected, status `ok` |
| R-58 | SHOULD | Active-card count = cards after visibility and supersession, before removing cards with unusable closures | contract:88 | A helper returns the count; a card with an unusable closure is still counted |

#### Legal selected set (six conditions) and feasibility

| ID | Level | Requirement | Source | Testable assertion |
|---|---|---|---|---|
| R-59 | MUST | Condition 1: every selected card is active and visible | contract:94 | Independent checker: `selected` is a subset of the recomputed active set |
| R-60 | MUST | Condition 2: every mandatory card is selected | contract:95 | Checker: `mandatory` is a subset of `selected` |
| R-61 | MUST | Condition 3: every selected card's full transitive `requires` closure is selected; shared requirements charged once | contract:96 | Checker: for each selected card, every `requires` entry is selected; `tokens` counts each card once |
| R-62 | MUST | Condition 4: at most one selected card per non-null `conflict_group`; null imposes nothing | contract:97 | Checker: non-null groups of selected cards are pairwise distinct |
| R-63 | MUST | Condition 5: no supplied pair has both endpoints selected | contract:98 | Checker: for every pair, not both in `selected` |
| R-64 | MUST | Condition 6: sum of `tokens` over distinct selected cards <= `budget`; equality allowed; coverage overlap gives no discount | contract:99 | Checker: recomputed sum <= budget; a set that exactly fills the budget is accepted |
| R-65 | MUST | Mandatory closure violating any condition gives `infeasible`; otherwise the request is feasible and the closure is itself legal | contract:101 | Mandatory closure over budget: `infeasible`. Mandatory closure legal: `ok` and closure is a subset of `selected` |
| R-66 | MUST | Empty `mandatory` always permits the empty selection, including at budget 0 | contract:101 | `mandatory: []`, `budget: 0`: status `ok`, `selected: []`, `tokens: 0` |
| R-67 | MUST | Never report `infeasible` because a heuristic found nothing | contract:101, :157 | For every request whose mandatory closure is legal, status is `ok` (property test against the checker) |

#### Objective and response

| ID | Level | Requirement | Source | Testable assertion |
|---|---|---|---|---|
| R-68 | MUST | Utility = sum of weights of the union of `covers` of selected cards; a repeated feature counts once | contract:105 | Two selected cards sharing a feature: `utility` counts its weight once |
| R-69 | MUST | Card count and budget use are not rewards | contract:105 | The objective comparison uses utility alone; a lower-utility fuller set is never preferred |
| R-70 | MUST | `ok` shape: exactly `status`, `selected`, `tokens`, `covered`, `utility`; only `certificate` may be added | contract:110, :113 | Key set of an `ok` response equals those five, optionally plus `certificate` |
| R-71 | MUST | `selected` and `covered` hold distinct IDs in ascending ASCII order | contract:113 | Each equals `sorted(set(x))`; `card10` sorts before `card2` |
| R-72 | MUST | `tokens` and `utility` are nonnegative integers, not booleans, and equal the values recomputed from `selected` | contract:113, :122 | `type(v) is int`; checker recomputation matches both |
| R-73 | MUST | `covered` equals the union of `covers` over `selected` | contract:105, :122 | Checker recomputation matches |
| R-74 | MUST | `invalid` and `infeasible` shapes: exactly `status` and a nonempty string `reason` | contract:118-119 | Key set is `{status, reason}`; `reason` is a non-empty `str` |
| R-75 | MUST | Invalid outranks infeasible | contract:122 | Request both infeasible (mandatory over budget) and invalid (duplicate pair) gives `invalid` |
| R-76 | OPTIONAL | Ties need no cost minimization or ID preference | contract:113 | No assertion; any maximum-utility legal set passes |

#### Optional utility upper-bound certificate

| ID | Level | Requirement | Source | Testable assertion |
|---|---|---|---|---|
| R-77 | OPTIONAL | `certificate` holds exactly `scale`, `budget_price`, `feature_prices` | contract:126-130 | Key set equals those three |
| R-78 | OPTIONAL | `scale`: integer 1-1,000,000, not boolean | contract:128, :132 | `type is int` and in range |
| R-79 | OPTIONAL | `budget_price`: nonnegative integer <= `scale` * sum of all feature weights | contract:129 | Range check with exact integers |
| R-80 | OPTIONAL | `feature_prices`: exactly every feature ID in `features`; each a nonnegative integer <= weight * `scale` | contract:130 | Key set equals `features` keys, including features no card covers; each in range |
| R-81 | OPTIONAL | Bound: `U = budget*p + sum over active visible cards of max(0, sum(z[f] for f in covers) - p*tokens) + sum over all features of (features[f]*s - z[f])`, exact integers | contract:134-139 | Checker recomputes `U` with Python ints; the card sum runs over active cards only, including those with unusable closures |
| R-82 | OPTIONAL | Tight gap: `100 * U <= 105 * utility * s` | contract:141 | Inequality holds on every profile instance in the corpus |
| R-83 | OPTIONAL | Tight-gap profile: every card (active or not) has empty `requires` and null `conflict_group`; `contradictions` empty; no feature covered by more than one active card | contract:143 | A profile detector flags exactly the requests meeting all three conditions |
| R-84 | MUST | A bad certificate fails only the optional capability, but any other extra field breaks the core schema; no certificate on `invalid` or `infeasible` | contract:145 | Non-`ok` responses never carry `certificate`; no response carries any other extra key |

#### Execution envelope and quality bars

| ID | Level | Requirement | Source | Testable assertion |
|---|---|---|---|---|
| R-85 | MUST | Runs on Linux, Python 3.11, standard library only, no network | contract:149, brief:27 | Import scan finds only stdlib and local modules; run passes in a `--network none` container |
| R-86 | MUST | 5 s wall per invocation including interpreter startup | contract:149, :157 | Recorder wall time < 5 s for all 28 instances on the 2-vCPU container |
| R-87 | MUST | 256 MiB peak RSS | contract:149, :157 | Recorder peak RSS < 256 MiB for all 28 instances |
| R-88 | MUST | 2 vCPUs means an effective quota or affinity, not visible CPU count; keep the recorder's CPU-capacity metadata and describe added restrictions | contract:149 | `benchmark_results.json` records a cgroup quota of 2 CPUs; README states the restriction used |
| R-89 | MUST | Exact maximum utility for requests with at most 24 active cards | contract:151 | Solver utility equals a brute-force oracle on random and corpus requests with <= 24 active cards |
| R-90 | MUST | Larger assessed requests: `100 * utility >= 99 * comparison_utility`, integer arithmetic | contract:151 | Against the best utility known to the project (independent method or bound), the inequality holds on every instance above 24 active cards |
| R-91 | OPTIONAL | 99.5% target: `200 * utility >= 199 * comparison_utility` | contract:151 | Same check with the tighter inequality |
| R-92 | OPTIONAL | Efficiency on valid feasible requests with >= 250 active cards: p95 (nearest rank `ceil(0.95*n)`) <= 750 ms and max RSS <= 64 MiB, with main quality retained | contract:153 | Compute nearest-rank p95 and max RSS from the recorder output over that subset |
| R-93 | OPTIONAL | Consistency across equivalent requests with utilities `L <= H`: `200 * (H - L) <= H` | contract:153, :7 | For each set of equivalent corpus requests, and for shuffled/renamed copies, the inequality holds |
| R-94 | MUST | All-member gate: one missing, malformed, timed-out, illegal or wrongly infeasible response fails its whole group | contract:157 | Legality checker passes on all 28 recorded responses; zero timeouts; zero parse failures |
| R-95 | MUST | Keep the recorder and its output unchanged; disclose unverified environment facts rather than presenting estimates as runs | contract:155, :157, notes:11 | Shipped recorder SHA-256 equals the baseline; README separates measured from estimated |

## Codebase References

- docs/task-brief.md — the assignment, verbatim
- docs/orchestrator-notes.md — prior direct read; two statements corrected above (class counts, mid-range target)
- docs/research-prompt.md — this research brief
- resources/director_context_contract.md — binding spec
- resources/director_usage_notes.md — product notes; README content rules
- resources/director_session.json — sample session; optimum 61
- resources/benchmark_runner.py — recorder; read as text only
- resources/benchmark_inputs.json — corpus; census only, never Read
- .claude-hve-tracking/research/subagents/2026-10-11/director-context-picker-contract.md — theme A (matrix, A-01..A-20, N-01..N-09)
- .claude-hve-tracking/research/subagents/2026-10-11/director-context-picker-recorder.md — theme B (recorder walk, output key structure)
- .claude-hve-tracking/research/subagents/2026-10-11/director-context-picker-corpus.md — theme C (sample hand walk, method-class facts)
- /Users/kevin/Documents/openartcontextpicker-orchestrator/census-2026-10-11.txt and census2-2026-10-11.txt — parent census output, outside the repo

## External References

None.

## Open Questions

1. Does `benchmark_inputs.json` ship in the ZIP? The brief does not list it; a clean-extraction rerun and any utility recomputation need it. Plan decision.
2. What is the recorder's RSS floor for `peak_rss_kib` in the container? Needed before reading anything against 64 MiB. Measure in the implement phase with the real solver.
3. How good is a greedy-plus-local-search answer on the six unit-weight coupled instances, where the 99% bar allows a deficit of only one to four cards? Unknown until measured; there is no public comparison utility, so the only evidence available is an upper bound and agreement between independent search runs.
4. Are the three signature-matched large pairs truly equivalent up to renaming and reordering? Not proven; treat as likely and test consistency on them and on shuffled or renamed copies.
5. Exactness at 19 to 24 active cards with adversarial topology (no constraints, shared features, loose budget) must hold inside 5 s in pure Python; the public corpus has no such instance. The plan needs a bound and a stress test.
6. The Python parser defaults listed above were recalled, not executed. Verify each in the validation phase's tests.

## Recommended Research Follow-On

- [ ] Plan: accept or decline each optional capability (certificate, 750 ms p95 with 64 MiB, 99.5%, consistency) in writing
- [ ] Plan: decide ZIP contents (inputs file in or out) and the package layout, given the recorder hashes every `.py` beside the solver
- [ ] Implement: tests for supersession chains, merges, invisible superseders, 19 to 24 active exactness, contract-maximum sizes
- [ ] Implement: after the recorded run, check by exact key `runner_sha256`, `inputs_sha256`, `python_sources_unchanged`, `environment.cpu_capacity.quota_vcpus` = 2.0, every `timed_out` false, every `response_parse_error` null, every `exit_code` 0
- [ ] Owner: docs/orchestrator-notes.md has two statements this research does not support (9/11 class split; "no target" for 25 to 249 active cards)

Agent types (addendum): the research-complete gh-tracker sync was delegated to a non-roster `general-purpose` subagent on the sonnet tier (name `gh-sync-research`), because the sync is mechanical GitHub bookkeeping that would otherwise block the plan phase in the parent; the orchestrator playbook routes gh-tracker syncs this way.
