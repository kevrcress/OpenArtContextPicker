# Orchestrator Notes: Director Context Picker

Written 2026-10-11 12:30 PDT from a direct read of the four small files in `resources/` and a read-only census of `resources/benchmark_inputs.json`. Nothing in `resources/` was executed. Citations name the section or function, since this is a living doc.

## Time

The ZIP is due 2026-10-11 15:30 PDT. The contract is 158 lines and is summarized below, so research is confirmation and gap-filling, not discovery. Suggested split from kickoff: research 15 min, plan 20 min, implement and test 80 min, Linux benchmark run 15 min, README and ZIP 20 min, 30 min held back.

## The benchmark must be recorded on Linux at 2 vCPUs

- The recorder's module docstring says "Run on Linux". The contract's `Execution, quality and observations` section sets the envelope: Linux, 2 vCPUs, Python 3.11, no network, 5 s wall per invocation including startup, 256 MiB peak RSS.
- The contract says a visible CPU count is not evidence; the recorder's `cpu_capacity` reads `/sys/fs/cgroup/cpu.max`. A run on the macOS host records no quota and is not a measured two-vCPU result.
- Docker is available on this machine: 29.1.3, `linux/aarch64`, 8 CPUs, 4 GB. No Python image is pulled yet. Pull `python:3.11-slim` early; it needs network and is the only step that does.
- Run the recorder in a container with `--cpus=2 --network none`. Do not cap container memory at 256 MiB: that limit applies to the solver's peak RSS, and the recorder itself loads an 8.4 MB corpus.
- The architecture is arm64, not x86. Disclose it in the README. The contract requires stating what was measured versus estimated.

## Recorder behavior that constrains the workflow

- `main` writes one file, the `--output` path. That is `benchmark_results.json`. It prints one JSON line per instance to stdout; `benchmark_run.log` is the operator's capture of stdout and stderr. This settles the duplicated description in the brief.
- Arguments: `--solution`, `--inputs`, `--output`, `--timeout` (default 5.0; leave it).
- `source_inventory` hashes every `*.py` under the solver's folder, recursively, before and after the run. `main` also records `runner_sha256`, `entrypoint_sha256` and `inputs_sha256`. Any edit to any `.py` file after the run makes the results stale. The recorded run is the last step before packaging, and it runs from a clean extraction of the package, not from the working tree.
- `environment.invocation` stores `sys.argv` verbatim. Use relative paths so no host path is recorded.
- The recorder passes each request through `canonical` (re-serialized, sorted keys) before the solver sees it. Duplicate JSON keys and odd whitespace in the corpus never reach the solver through the recorder. Those cases need the project's own tests.
- The docstring requires the recorder be retained unchanged. Ship a byte-identical copy in the ZIP.

Integrity baseline (SHA-256):

| File | SHA-256 |
|---|---|
| `resources/benchmark_runner.py` | `87694477eca9636ed78766d4473821befb9d388bf2444b2e1b5310f5e6ca5943` |
| `resources/benchmark_inputs.json` | `164ea460ed919a4e5e365c5357b9d53606f8f5fb53df8c238664c8117eae541c` |
| `resources/director_context_contract.md` | `10267a9c8acb1a1753f38e552c72958623abceaeb8524916e2811874060928ed` |
| `resources/director_session.json` | `532851d06162a80706a110fdb3cc2aed278c42637daf3eb2e744e29e62bb0b3a` |
| `resources/director_usage_notes.md` | `3f3d658e0ae39febf48096e641336b5b075add22ef0d69dfd91fdca0304c34ef` |

`runner_sha256` and `inputs_sha256` in the final `benchmark_results.json` must equal the first two rows.

## What the problem is

From the contract's `Legal selected set` and `Objective and response` sections:

- Maximize the summed weight of distinct covered features, subject to a token budget.
- Only cards that are visible from `head` and not superseded by a visible card are selectable.
- `requires` closures are selected whole (cycles allowed). At most one card per non-null `conflict_group`. No contradiction pair with both ends selected; pairs are not transitive and never transfer to a successor card. Every `mandatory` card is selected.
- Three statuses: `ok`, `invalid`, `infeasible`. All exit 0. Validation outranks infeasibility. Diagnostics go to stderr; stdout carries exactly one JSON object and a newline.

This is budgeted maximum coverage with dependency closures and a conflict graph. It is NP-hard in general, so the contract sets two quality bars (`Execution, quality and observations`):

- Exact maximum utility at 24 or fewer active cards.
- At least 99% of a hidden feasible comparison utility at 250 to 500 active cards.

Each quality group is all-or-nothing: one illegal, malformed, timed-out or wrongly infeasible response fails the whole group. Legality and validation come before utility tuning.

Optional capabilities, to be accepted or declined explicitly in the plan: the utility upper-bound certificate, 750 ms p95 with 64 MiB RSS, the 99.5% target, and consistency across equivalent requests.

## Validation cases the standard `json` module accepts by default

The contract's `Input` section makes each of these `invalid`:

- Duplicate object keys (needs `object_pairs_hook`).
- Integers written as `1.0` or `1e2`; booleans where integers are required.
- `NaN` and `Infinity`.
- Raw input over 16 MiB; input that is not valid UTF-8; anything after the one JSON object.
- Unknown keys at any level; identifiers outside the allowed ASCII pattern or 1 to 64 characters.
- A supersession that is not from a strict ancestor version; a cyclic version graph.

Deeply nested input raises `RecursionError` in the parser. Catch it and return `invalid`.

## Corpus census

28 instances, schema `openart-context-inputs/2`. No expected outputs are supplied; the recorder's docstring says it holds no grading answers. Correctness needs a brute-force oracle for small cases and an independent legality checker, both written in this repo.

| Group | Count | Active cards | Notes |
|---|---|---|---|
| Tiny probes | 9 | 2 to 3 | Budget 100; each probes one rule (pairs, groups, requires, mandatory, branch visibility) |
| Small, exactness range | 3 | 12, 16, 18 | Requires, groups and pairs all present |
| Mid | 3 | 36, 48, 64 | Above 24 and below 250; the contract names no target for this range |
| Large coupled | 11 | 284 to 476 | 5 versions, 1 mandatory card, 1,904 to 7,424 pairs, almost every card has `requires` |
| Large unconstrained | 2 | 256, 320 | No requires, groups or pairs; one feature per card; this is the certificate profile |

Several large instances share an identical serialized size (for example three at 351,136 bytes), which suggests equivalent repeats for the consistency check. Research confirms or refutes this.

`resources/benchmark_inputs.json` is 8.4 MB. Do not Read it into context. `hve-researcher` subagents have no shell, so the parent runs the census and passes results in.

## Rules from the product notes

From `resources/director_usage_notes.md`:

- No LLM calls. No inferring contradictions from text. No silent repair of invalid requests.
- The README operational note covers handling of bad upstream metadata, a safe fallback, and the limits of the union-coverage objective.
- No claims about OpenArt production behavior from benchmark numbers. Separate measurements from estimates.

## Environment

- Use `python3.11` by name on the host. `python3` is 3.14.7.
- `resources/` stays byte-identical. Build the package from copies.
- Global HVE rule: run every test gate as `<cmd> > gate.log 2>&1; echo rc=$?` and read the exit code. `gate.log` is gitignored.
