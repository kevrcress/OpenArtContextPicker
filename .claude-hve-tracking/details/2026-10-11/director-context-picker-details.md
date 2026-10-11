# Implementation Details: Director context picker
Date: 2026-10-11
Task slug: director-context-picker
Plan: .claude-hve-tracking/plans/2026-10-11/director-context-picker-plan.md

Everything here is binding on the phase that owns the file. Interfaces are fixed so phases can run in parallel; do not rename a function, change a signature or add a module-level dependency on a file another phase owns beyond what is listed.

## 1. Layout (repo root is the package root and mirrors the ZIP root)

Flat modules, no package directory, no `__init__.py` anywhere. Python 3.11 standard library only. Always run with `python3.11` on the host.

| Path | Owner phase | Purpose |
|---|---|---|
| `dcp_validate.py` | 1 | strict input validation |
| `tests/test_validate.py` | 1 | |
| `dcp_model.py` | 2 | active set, closures, masks, mandatory feasibility, evaluation |
| `tests/test_model.py` | 2 | |
| `tests/checker.py`, `tests/oracle.py`, `tests/gen.py`, `tests/test_checker_oracle.py` | 3 | independent legality checker, brute-force oracle, request generators |
| `tools/build_package.py`, `tools/run_recorded.sh`, `tools/check_results.py`, `tools/make_zip.py`, `tests/test_tools.py` | 4 | packaging, Docker recorded run, post-run checks |
| `dcp_exact.py`, `tests/test_exact.py` | 5 | exact branch and bound |
| `dcp_search.py`, `tests/test_search.py`, `tools/tune_search.py` | 6 | greedy plus local search for large instances |
| `dcp_profile.py`, `tests/test_profile.py` | 7 | exact knapsack and certificate for the certificate profile |
| `context_solver.py`, `dcp_pipeline.py`, `tests/test_cli.py`, `tests/test_corpus.py` | 8 | CLI, dispatch, fallback, corpus regression |
| `benchmark_results.json`, `benchmark_run.log` | 9 | recorder output, copied from the run directory unedited |
| `README.md` | 10, then 11 | 10 writes it with number placeholders marked `TBD-MEASURED`; 11 fills them |
| `director-context.zip` (gitignored) | 11 | |

Test command (the README's regression command), run from the package root:

```
python3.11 -m unittest discover -s tests -v
```

`python -m unittest` puts the current directory on `sys.path` (root modules import as `import dcp_model`) and `discover -s tests` puts `tests/` on it (helpers import as `import checker`, `import oracle`, `import gen`). A phase runs only its own test file while other phases are in flight, in this form (the direct-path form leaves `tests/` off `sys.path`): `python3.11 -m unittest discover -s tests -p 'test_validate.py' -v`. Gates run as `<cmd> > gate.log 2>&1; echo rc=$?`.

Tests must not need Docker or network. `tests/test_corpus.py` looks for the corpus at `./benchmark_inputs.json`, then `./resources/benchmark_inputs.json`; if neither exists it FAILS (it does not skip).

## 2. `dcp_validate.py` (Phase 1)

```python
MAX_BYTES = 16 * 1024 * 1024

class InvalidRequest(Exception):
    """str(exc) is a nonempty ASCII reason."""

def validate_request(raw: bytes) -> dict:
    """Return the request as plain dict/list/str/int/None exactly as parsed, or raise InvalidRequest.
    Never raises anything else: wrap the body and convert RecursionError, ValueError, MemoryError,
    UnicodeDecodeError and any other Exception into InvalidRequest."""
```

Rules (research R-01..R-60 and A-01..A-20; contract lines cited there):

- `len(raw) > MAX_BYTES` is invalid; exactly `MAX_BYTES` is allowed. Check before decoding.
- Decode with `raw.decode("utf-8", errors="strict")`. Never pass bytes to `json.loads`. A leading BOM (`﻿`) is invalid.
- Parse with `json.JSONDecoder(object_pairs_hook=..., parse_float=..., parse_constant=...)` and `raw_decode` after stripping leading JSON whitespace (space, `\t`, `\n`, `\r` only); anything other than JSON whitespace after the object is invalid. Empty or whitespace-only input is invalid.
- `object_pairs_hook` rejects duplicate keys at every level. `parse_float` rejects every float-notation number (`1.0`, `1e2`). `parse_constant` rejects `NaN`, `Infinity`, `-Infinity`.
- Integers: `type(x) is int` (booleans are not integers). Integer literals over 4,300 digits raise `ValueError` in 3.11: invalid.
- Top level: a JSON object with exactly the seven keys `versions, cards, features, head, budget, mandatory, contradictions`. Unknown or missing key: invalid.
- Identifier: `re.fullmatch(r"[A-Za-z0-9._:\-]{1,64}", s)` on a `str`. Version, card, feature and group IDs are separate namespaces.
- `versions`: list of 1..96 dicts, keys exactly `id, parents`; unique ids; `parents` a list of 0..8 distinct existing version ids; graph acyclic (a version listing itself as parent is a cycle).
- `cards`: list of 0..500 dicts; required keys `id, version, supersedes, requires, conflict_group, tokens, covers`; optional `text`; no other key. Unique ids. `version` an existing version id. `supersedes` and `requires`: lists of 0..8 distinct existing card ids. `conflict_group`: `None` or identifier. `tokens`: int 1..512. `covers`: list of 0..64 distinct existing feature ids. `text`: `str`, `len(text) <= 2048` code points.
- Supersession: a card cannot supersede itself; for every `(c supersedes o)`, `o.version` must be a strict ancestor of `c.version` in the whole version graph (independent of `head`). Same version or unrelated branch: invalid. Self-requirement and requirement cycles are valid.
- `features`: dict of 0..1024 identifier keys to int 1..1000.
- `head`: existing version id. `budget`: int 0..8192. `mandatory`: list of distinct existing card ids.
- `contradictions`: list of 0..10000 items, each a list of exactly two `str` existing card ids, the two different; no unordered pair repeated in either orientation.
- `None` appears only as `conflict_group`.
- All validation completes before any feasibility reasoning. Reasons are short ASCII strings authored here; never echo request text into a reason.

## 3. `dcp_model.py` (Phase 2)

Input is a dict already accepted by `validate_request` (tests build dicts by hand; do not import `dcp_validate`).

```python
from dataclasses import dataclass

class Infeasible(Exception):
    """str(exc) is a nonempty ASCII reason. Raised only when the mandatory closure is not a legal set."""

@dataclass(frozen=True)
class Problem:
    budget: int
    n: int                    # the contract's active-card count (visible, not superseded), before usability
    ids: tuple                # active card ids sorted ascending; bit i <-> ids[i]
    tokens: tuple             # tokens[i]
    feat_ids: tuple           # ALL feature ids of the request, sorted ascending; feature index f
    feat_w: tuple             # feat_w[f]
    cover: tuple              # cover[i]: int bitmask over feature indices
    closure: tuple            # closure[i]: bitmask over active cards, transitive requires closure incl. i; 0 if it leaves the active set
    conflict: tuple           # conflict[i]: bitmask of active cards that cannot be selected with i (pair, or same non-null group), never includes i
    closure_tokens: tuple     # token sum of closure[i]
    closure_cover: tuple      # OR of cover[j] for j in closure[i]
    closure_conflict: tuple   # OR of conflict[j] for j in closure[i]
    dependents: tuple         # dependents[i]: bitmask of active cards j with closure[j] containing i (includes i)
    mandatory: int            # bitmask: union of closures of mandatory cards; a legal set by construction
    usable: int               # bitmask of cards i NOT in mandatory whose closure can be added to the mandatory set legally

def build_problem(req: dict) -> Problem: ...      # raises Infeasible
def mask_tokens(p: Problem, mask: int) -> int: ...
def mask_cover(p: Problem, mask: int) -> int: ...   # feature bitmask
def cover_weight(p: Problem, fmask: int) -> int: ...
def is_legal(p: Problem, mask: int) -> bool: ...    # all six contract conditions, on masks
def mask_ids(p: Problem, mask: int) -> list: ...    # selected ids, ascending
def fmask_ids(p: Problem, fmask: int) -> list: ...  # covered feature ids, ascending
```

Semantics:

- Visible versions: `head` and all transitive ancestors (DAG walk, iterative, not recursive). Visible card: its version is visible.
- Active: visible and not reachable through `supersedes` edges (one or more hops) from any visible card. An invisible card never deactivates anything.
- Pairs and `requires` refer to exact card ids. A pair with an inactive endpoint constrains nothing. A `requires` on an inactive or invisible card makes the dependent's closure leave the active set: `closure[i] = 0`, card unusable. Never redirect to a successor.
- `usable` excludes card i when: `closure[i] == 0`; or `closure_conflict[i] & closure[i]` (pair or same group inside the closure); or `closure_conflict[i] & mandatory`; or `mask_tokens(closure[i] | mandatory) > budget`. Unusable cards still count in `n`.
- `Infeasible` when a mandatory card is not active, its closure leaves the active set, the mandatory union has an internal conflict, or its tokens exceed the budget. Empty `mandatory` gives `mandatory == 0`, always feasible, including at budget 0.
- Legal mask S: `S & mandatory == mandatory`; for every i in S `closure[i] != 0` and `closure[i] & ~S == 0`; for every i in S `conflict[i] & S == 0`; `mask_tokens(S) <= budget`.
- Recursion is forbidden (closures can be 500 deep): use explicit stacks.
- Performance target: `build_problem` on a 488-card, 7,424-pair request in under 60 ms on the host.

## 4. `tests/checker.py`, `tests/oracle.py`, `tests/gen.py` (Phase 3)

Independent of every `dcp_*` module: these files import nothing from the solver. They work on the raw request dict with sets and dicts, not bitmasks, so a shared bug is unlikely.

```python
# checker.py
def active_cards(request: dict) -> set: ...
def expected_feasible(request: dict) -> bool: ...        # False when the mandatory closure is not legal
def check_response(request: dict, response: dict) -> list:  # list of error strings; empty means the response is correct in form and legal
    """Checks: exact key sets per status; types (bool is not int); selected and covered distinct, ASCII-ascending;
    six legality conditions; tokens and utility and covered recomputed and equal; status ok only if expected_feasible;
    infeasible only if not expected_feasible; certificate (when present) only on ok, exact keys, ranges, feature_prices
    covers exactly every feature id."""
def certificate_bound(request: dict, certificate: dict) -> tuple:  # (U, s) by the contract formula, exact integers, sum over ACTIVE cards
def is_certificate_profile(request: dict) -> bool: ...   # contract "tight-gap capability" conditions

# oracle.py
def best_utility(request: dict, limit: int = 20) -> int:
    """Exhaustive maximum over all subsets of active cards (raises ValueError when len(active) > limit).
    Raises LookupError when no legal set exists."""

# gen.py
def random_request(rng, n_cards, *, n_versions=1, p_requires=0.3, p_group=0.3, n_pairs=None, p_supersede=0.0,
                   n_features=None, max_covers=3, max_tokens=40, budget_ratio=0.5, n_mandatory=0) -> dict:
    """Always returns a request that satisfies the input contract (valid), feasible or not."""
def max_request(rng, *, profile: bool = False) -> dict:
    """A valid request at the contract maxima: 500 active cards, 96 versions in a chain with head at the tip, 1,024 features,
    up to 64 covers per card, tokens up to 512, budget 8,192, and (unless profile) 10,000 pairs, a 200-card requires chain,
    one requires cycle and 20 groups. With profile=True: no requires, groups or pairs, one distinct feature per card."""
def permute_request(rng, request: dict) -> dict:
    """An equivalent request: card, version, feature and group ids renamed by a random bijection, every array shuffled,
    pair orientation flipped at random."""
```

`tests/test_checker_oracle.py` must pin: the sample session `resources/director_session.json` (fall back to an inline copy when the file is absent in the package) has 7 active cards and `best_utility` 61; the seven tiny corpus requests reproduced inline from the research document have these outcomes: i_353b… ok 60, i_5568… ok 70, i_f4bb… ok 70 with selected `["b","c"]`, i_6bf2… and i_354f… infeasible; a deliberately illegal response for each of the six conditions is rejected by `check_response`.

## 5. `dcp_exact.py` (Phase 5)

```python
def solve_exact(p, deadline: float, incumbent: int | None = None) -> tuple:
    """Return (mask, proven). mask is always a legal set (at least p.mandatory). proven is True when the search
    space was exhausted before `deadline` (a time.perf_counter() value)."""
```

- Depth-first branch and bound over cards in `p.usable`. State: selected mask S (starts at `p.mandatory`), excluded mask X, tokens, covered feature mask F, utility.
- Branch card c: include (`S |= closure[c]`, allowed when `closure_conflict[c] & S == 0`, `closure[c] & X == 0`, tokens fit) or exclude (`X |= dependents[c]`).
- Eligible card at a node: not in S, not in X, `conflict[c] & S == 0`, `tokens[c] <= budget - tokens(S)`. (Every card that any legal extension of S avoiding X could add is eligible; the set is a superset on purpose.)
- Upper bound at a node, both valid, take the smaller: (a) utility plus the weight of features covered by eligible cards and not yet in F; (b) utility plus the integer floor of a fractional-knapsack bound over eligible individual cards with value `cover_weight(cover[c] & ~F)` and weight `tokens[c]` against the remaining budget. (b) is valid because coverage is subadditive and a set of added cards costs exactly the sum of their own tokens.
- Including c costs `mask_tokens(closure[c] & ~S)` and must fit the remaining budget.
- Seed the incumbent with a simple greedy (own code; do not import `dcp_search`), or with `incumbent` when given and legal.
- Iterative or recursion depth at most the number of usable cards (at most 500; keep recursion under 600 frames or use an explicit stack). Check the deadline every 256 nodes.
- Must be exact for every request with `p.n <= 24`. Success is measured against `oracle.best_utility` on generated requests and by a stress test at 24 active cards.

## 6. `dcp_search.py` (Phase 6)

```python
def solve_large(p, deadline: float, seed: int = 20261011) -> int:
    """Return a legal mask (at least p.mandatory). Runs until `deadline` (time.perf_counter() value) at the latest."""
```

- Construction: greedy from `p.mandatory`, repeatedly adding the usable card c with the best marginal weight per marginal token of `closure[c] & ~S` (also try best marginal weight; keep the better result). Ties break on the lower index.
- Improvement, until the deadline: iterated ejection and refill with `random.Random(seed)`. Pick a card c in `p.usable` outside S; compute the eviction set (selected cards in `closure_conflict[c]`, expanded through `dependents` restricted to S; skip the move when it touches `p.mandatory`); form `(S - evicted) | closure[c]`; while over budget drop the selected non-mandatory unit with the worst lost-weight per freed token (dropping a card drops its selected dependents); refill greedily; accept when utility does not decrease (ties accepted, to drift across plateaus), keep the best seen. Mix in a random-removal perturbation when no improvement for a while. Maintain per-feature cover counts incrementally; do not recompute utility from scratch per move.
- Check the clock at most every 32 moves. Return the best legal mask seen. Assert `is_legal` before returning and fall back to the greedy result, then to `p.mandatory`.
- `tools/tune_search.py` (owned here): for each public instance with at least 25 active cards, run `solve_large` with deadlines 0.3, 1.0, 2.0 s and a 20 s reference run with three seeds; print a table of utilities. Used for the success criterion and for the README. Reads the corpus from `resources/benchmark_inputs.json`.

## 7. `dcp_profile.py` (Phase 7)

```python
def profile_applies(req: dict, p) -> bool:
    """Contract tight-gap profile: every card in req (active or not) has requires == [] and conflict_group is None;
    req["contradictions"] == []; no feature is covered by more than one ACTIVE card."""
def solve_profile(p, deadline: float) -> int | None:
    """Exact 0/1 knapsack over usable cards with p.mandatory forced. None when the deadline would be exceeded."""
def build_certificate(p, mask: int) -> dict | None:
    """A certificate satisfying the contract schema with 100*U <= 105*utility*s, or None when no such certificate is found."""
```

- Knapsack DP over capacity `budget - tokens(mandatory)`, values `cover_weight(cover[i])`; skip zero-value cards. Per item use list comprehensions over slices (no per-cell Python loop) and store one `bytes` decision row per item for reconstruction. Worst case 500 × 8,192 cells must finish inside the deadline or return `None`.
- Certificate: `feature_prices[f] = feat_w[f] * scale` for every feature id; candidates for `(scale, budget_price)` are `(tokens_k, value_k)` for the fractional-greedy break card k over ALL active cards sorted by value/tokens, its neighbors in that order, and `(1, 0)`; compute `U = budget*p + sum over active cards of max(0, sum(z[f] for f in covers) - p*tokens) + sum over features of (w*s - z)` exactly; pick the smallest `U/s`; return it only when ranges hold (`1 <= scale <= 1_000_000`, `0 <= budget_price <= scale * sum(weights)`) and `100*U <= 105*utility*scale`.

## 8. `dcp_pipeline.py` and `context_solver.py` (Phase 8)

```python
# dcp_pipeline.py
EXACT_MAX_ACTIVE = 24
EXACT_DEADLINE_S = 3.5     # seconds after process start
LARGE_DEADLINE_S = 2.5     # seconds after process start; final value set by step 8.6 from measurements
MID_EXACT_MAX_ACTIVE = 64  # above 24 and up to this, run the exact search after the heuristic with the time left
MID_SEARCH_DEADLINE_S = 1.0  # heuristic share for 25..64 active cards; the exact pass gets the rest up to LARGE_DEADLINE_S

def run(raw: bytes, t0: float) -> dict:   # never raises
```

Order: `validate_request` (InvalidRequest → `{"status":"invalid","reason":...}`) → `build_problem` (Infeasible → `{"status":"infeasible","reason":...}`) → choose method → response.

- Method: `profile_applies` → `solve_profile(p, t0 + LARGE_DEADLINE_S)`; on `None` fall through. `p.n <= 24` → `solve_exact(p, t0 + EXACT_DEADLINE_S)`. `25 <= p.n <= MID_EXACT_MAX_ACTIVE` → `solve_large(p, t0 + MID_SEARCH_DEADLINE_S)` then `solve_exact(p, t0 + LARGE_DEADLINE_S, incumbent=that mask)`. Otherwise `solve_large(p, t0 + LARGE_DEADLINE_S)`.
- Any exception from a solver is written to stderr and the best legal mask so far is kept; the floor is `p.mandatory`. The final mask is checked with `is_legal`; an illegal mask is replaced by `p.mandatory`.
- Response for ok: `{"status":"ok","selected":[...],"tokens":int,"covered":[...],"utility":int}` plus `certificate` only when `profile_applies` and `build_certificate` returned one. Exact key sets; no other field.
- `context_solver.py`: record `t0 = time.perf_counter()` first; read `sys.stdin.buffer.read(MAX_BYTES + 1)` (drain and discard anything beyond); write `json.dumps(resp, separators=(",", ":"), ensure_ascii=True) + "\n"` to stdout once; diagnostics (method, active count, elapsed ms, proven flag) to stderr as one short line; exit 0. A last-resort `except BaseException` around everything prints `{"status":"invalid","reason":"internal error"}` when validation had not completed. When validation passed and `build_problem` itself raised something other than `Infeasible`, there is no model to fall back on: write the traceback to stderr and print `{"status":"invalid","reason":"internal error: model construction failed"}` (a wrong answer either way; it is at least well formed). After `build_problem` succeeded, every failure path answers with the mandatory closure as `ok`.

## 9. Recorded run and packaging (Phases 4, 9, 11)

Package contents at the ZIP root: `context_solver.py`, `dcp_*.py`, `tests/`, `tools/`, `benchmark_runner.py` (byte-identical copy of `resources/benchmark_runner.py`), `benchmark_inputs.json` (byte-identical copy of `resources/benchmark_inputs.json`; 922,249 bytes when zipped at `-9`, measured), `director_session.json` (copy, used by a test), `benchmark_results.json`, `benchmark_run.log`, `README.md`. No `__pycache__`, no `.DS_Store`, no `.claude-hve-tracking`, no `docs/`, no `gate.log`.

- `tools/build_package.py --out build/pkg`: copy the files above from the repo (sources from the root, supplied files from `resources/`), refusing to run if any `resources/` hash differs from the baseline in the research document.
- `tools/run_recorded.sh <dir>`: runs, with `<dir>` mounted read-write at `/work`:

  ```
  docker run --rm --cpus=2 --network none -v "<dir>":/work -w /work python:3.11-slim sh -c 'python benchmark_runner.py --solution context_solver.py --inputs benchmark_inputs.json --output benchmark_results.json > benchmark_run.log 2>&1; echo rc=$?'
  ```

  No memory cap on the container. Removes `__pycache__` directories from `<dir>` afterwards.
- `tools/check_results.py <dir>`: reads `<dir>/benchmark_results.json` and the corpus; asserts `runner_sha256` and `inputs_sha256` equal the baseline, `python_sources_unchanged` true, `environment.cpu_capacity.quota_vcpus == 2.0`, 28 records; asserts for every record `exit_code == 0`, `timed_out` is false, `response_parse_error` is null, `stdout` is exactly one JSON object followed by one newline, `wall_ms < 5000` and `peak_rss_kib < 262144`; runs `tests/checker.check_response` on every record; prints per instance: id, active count, status, utility, tokens, wall_ms, peak_rss_kib, timed_out, checker verdict; prints p95 (nearest rank) and max RSS over valid feasible requests with at least 250 active cards, and the consistency ratio for the three repeat pairs. Exit code 1 when any integrity assertion or checker verdict fails.
- `tools/make_zip.py <dir> director-context.zip`: deterministic zip of `<dir>` with files at the archive root.
- Sequence in Phase 9: build package → zip a staging archive → extract it into a new empty directory → `run_recorded.sh` there → `check_results.py` there → copy `benchmark_results.json` and `benchmark_run.log` byte-for-byte into the repo root. Phase 11: fill README numbers → build package again (sources unchanged; the script must fail if any `.py` hash differs from `python_sources_after` in `benchmark_results.json`) → `make_zip.py` → extract into a new empty directory → run the regression command there → `check_results.py` there.

## 10. README content (Phases 10, 11)

Sections, in this order: what this is; clean-extraction commands (unzip, regression command, recorded-run command in Docker, single-request example); method (validation, model, exact search at 24 or fewer active cards, exact knapsack with certificate on the profile, greedy plus local search above 24, fallback to the mandatory closure); results on the public corpus (table produced by `tools/check_results.py`; every invalid, infeasible, failed or timed-out request listed); measurement environment (Docker `python:3.11-slim`, Python 3.11.17, linux/arm64 under Docker Desktop on an Apple-silicon host, `--cpus=2` recorded as `cgroup_cpu_max 200000 100000`, 8 logical CPUs visible, `--network none`, no memory cap, recorder unchanged with its SHA-256); measured versus estimated (no x86 run; no comparison utilities exist publicly, so the 99% bar is not measured; what evidence stands in for it); optional capabilities accepted and declined; limitations; operational note (bad upstream metadata is rejected as `invalid` and never repaired; safe fallback for the caller on `invalid`, `infeasible`, timeout or crash; limits of the union-coverage objective: model obedience, rendering overhead, semantic nuance, output continuity, production drift, a missed conflict upstream); no claims about OpenArt production behavior; the extractor, weights and tokenizer are assessment assumptions.
