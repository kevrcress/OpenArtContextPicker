"""Check a recorded benchmark run and print the measured numbers.

Usage: python3.11 tools/check_results.py <dir> [--json PATH] [--allow-wrong]

Reads ``<dir>/benchmark_results.json`` and ``<dir>/benchmark_inputs.json``, checks
the integrity fields and every record, judges each response with the independent
checker in ``tests/checker.py`` (loaded by path; the solver is never imported),
and prints a Markdown table plus summary figures. Exit code 1 when any integrity
assertion or checker verdict fails, unless ``--allow-wrong`` is given.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import sys
from pathlib import Path

RUNNER_SHA256 = "87694477eca9636ed78766d4473821befb9d388bf2444b2e1b5310f5e6ca5943"
INPUTS_SHA256 = "164ea460ed919a4e5e365c5357b9d53606f8f5fb53df8c238664c8117eae541c"
EXPECTED_RECORDS = 28
WALL_LIMIT_MS = 5000
RSS_LIMIT_KIB = 262144
LARGE_ACTIVE = 250
# The two public requests that break the input contract (measured in research).
# Hard-coded so this script never has to import the solver's validator.
KNOWN_INVALID_IDS = frozenset({"i_93a288225d57a93686", "i_57be790be38419e246"})
# Public repeat pairs: the same problem presented twice, used for the consistency ratio.
CONSISTENCY_PAIRS = (
    ("i_d377627acc7b53786a", "i_b05b69c48293a3d4b4"),
    ("i_613d784770e53c543d", "i_91a2e8f7679a6871f4"),
    ("i_27d35bf2cd22d3769a", "i_dfcebb3746dc9feecb"),
)


def load_checker(path: Path | None = None):
    """Load ``tests/checker.py`` by path (next to ``tools/`` in the repo and in the package)."""
    path = path or Path(__file__).resolve().parent.parent / "tests" / "checker.py"
    spec = importlib.util.spec_from_file_location("dcp_results_checker", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load the checker from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def canonical_sha256(value: object) -> str:
    """SHA-256 of the recorder's canonical JSON encoding of ``value``."""
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def stdout_is_one_object(stdout: object) -> bool:
    """True when ``stdout`` is exactly one JSON object followed by exactly one newline."""
    if type(stdout) is not str or not stdout.endswith("\n"):
        return False
    body = stdout[:-1]
    if not body or body != body.strip():
        return False
    try:
        return isinstance(json.loads(body), dict)
    except ValueError:
        return False


def nearest_rank_p95(values: list[float]) -> float | None:
    """The ``ceil(0.95 * n)``-th smallest value, or ``None`` for an empty list."""
    if not values:
        return None
    return sorted(values)[math.ceil(0.95 * len(values)) - 1]


def _record_problems(record: dict) -> list[str]:
    problems = []
    if record.get("exit_code") != 0:
        problems.append(f"exit_code {record.get('exit_code')!r}")
    if record.get("timed_out") is not False:
        problems.append("timed_out")
    if record.get("response_parse_error") is not None:
        problems.append("response_parse_error")
    if not stdout_is_one_object(record.get("stdout")):
        problems.append("stdout is not one JSON object plus one newline")
    wall, rss = record.get("wall_ms"), record.get("peak_rss_kib")
    if not isinstance(wall, (int, float)) or not wall < WALL_LIMIT_MS:
        problems.append(f"wall_ms {wall!r} not under {WALL_LIMIT_MS}")
    if not isinstance(rss, (int, float)) or not rss < RSS_LIMIT_KIB:
        problems.append(f"peak_rss_kib {rss!r} not under {RSS_LIMIT_KIB}")
    return problems


def evaluate(results: dict, corpus: dict, checker, *, runner_sha256: str = RUNNER_SHA256,
             inputs_sha256: str = INPUTS_SHA256, expected_records: int = EXPECTED_RECORDS,
             invalid_ids: frozenset = KNOWN_INVALID_IDS) -> dict:
    """Judge a results document against its corpus; return a JSON-ready summary."""
    integrity = []

    def expect(name: str, ok: bool, detail: str) -> None:
        integrity.append({"check": name, "ok": bool(ok), "detail": detail})

    env = results.get("environment", {})
    quota = env.get("cpu_capacity", {}).get("quota_vcpus")
    records = results.get("instances", [])
    requests = {item["id"]: item["request"] for item in corpus["instances"]}
    expect("runner_sha256", results.get("runner_sha256") == runner_sha256, str(results.get("runner_sha256")))
    expect("inputs_sha256", results.get("inputs_sha256") == inputs_sha256, str(results.get("inputs_sha256")))
    expect("python_sources_unchanged", results.get("python_sources_unchanged") is True,
           str(results.get("python_sources_unchanged")))
    expect("quota_vcpus == 2.0", quota == 2.0, str(quota))
    expect(f"{expected_records} records", len(records) == expected_records, str(len(records)))
    expect("record ids match the corpus in order", [r.get("id") for r in records] == list(requests),
           f"{len(records)} records, {len(requests)} corpus instances")

    rows, by_id = [], {}
    for record in records:
        rid = record.get("id")
        request = requests.get(rid)
        response = record.get("response")
        problems = _record_problems(record)
        valid = rid not in invalid_ids
        active = feasible = None
        cert_errors: list[str] = []
        if request is None:
            problems.append("id is not in the corpus")
        else:
            if record.get("input_sha256") != canonical_sha256(request):
                problems.append("input_sha256 does not match the corpus request")
            if valid:
                active = len(checker.active_cards(request))
                feasible = checker.expected_feasible(request)
            errors = checker.check_response(request, response, request_valid=valid)
            cert_errors = [e for e in errors if e.startswith("certificate:")]
            problems.extend(errors)
        is_ok = isinstance(response, dict) and response.get("status") == "ok"
        row = {
            "id": rid, "active": active, "valid": valid, "feasible": feasible,
            "status": response.get("status") if isinstance(response, dict) else None,
            "utility": response.get("utility") if is_ok else None,
            "tokens": response.get("tokens") if is_ok else None,
            "wall_ms": record.get("wall_ms"), "peak_rss_kib": record.get("peak_rss_kib"),
            "timed_out": record.get("timed_out"), "verdict": "pass" if not problems else "FAIL",
            "problems": problems, "certificate": None,
        }
        if (request is not None and valid and is_ok and "certificate" in response and not cert_errors
                and checker.is_certificate_profile(request) and type(row["utility"]) is int):
            bound, scale = checker.certificate_bound(request, response["certificate"])
            row["certificate"] = {"U": bound, "s": scale, "utility": row["utility"],
                                  "within_5_percent": 100 * bound <= 105 * row["utility"] * scale}
        rows.append(row)
        by_id[rid] = row

    status_counts: dict[str, int] = {}
    for row in rows:
        key = str(row["status"])
        status_counts[key] = status_counts.get(key, 0) + 1
    walls = [r["wall_ms"] for r in rows if isinstance(r["wall_ms"], (int, float))]
    large = [r for r in rows if r["valid"] and r["feasible"] and (r["active"] or 0) >= LARGE_ACTIVE]
    large_rss = [r["peak_rss_kib"] for r in large if isinstance(r["peak_rss_kib"], (int, float))]
    pairs = []
    for first, second in CONSISTENCY_PAIRS:
        utilities = [by_id.get(i, {}).get("utility") for i in (first, second)]
        entry = {"ids": [first, second], "L": None, "H": None, "within_half_percent": None}
        if all(type(u) is int for u in utilities):
            low, high = min(utilities), max(utilities)
            entry.update(L=low, H=high, within_half_percent=200 * (high - low) <= high)
        pairs.append(entry)

    failed = [r["id"] for r in rows if r["problems"]]
    return {
        "passed": all(c["ok"] for c in integrity) and not failed,
        "integrity": integrity, "rows": rows, "failed_ids": failed, "status_counts": status_counts,
        "max_wall_ms": max(walls) if walls else None,
        "large": {"min_active": LARGE_ACTIVE, "n": len(large),
                  "p95_wall_ms": nearest_rank_p95([r["wall_ms"] for r in large
                                                   if isinstance(r["wall_ms"], (int, float))]),
                  "max_peak_rss_kib": max(large_rss) if large_rss else None},
        "certificates": [dict(id=r["id"], **r["certificate"]) for r in rows if r["certificate"]],
        "consistency_pairs": pairs, "environment": env,
    }


def _cell(value: object) -> str:
    return "-" if value is None else str(value)


def render(summary: dict) -> str:
    """The Markdown report for a summary from ``evaluate``."""
    lines = ["## Integrity", ""]
    for check in summary["integrity"]:
        lines.append(f"- {'ok' if check['ok'] else 'FAIL'}: {check['check']} ({check['detail']})")
    lines += ["", "## Instances", "",
              "| id | active cards | status | utility | tokens | wall_ms | peak_rss_kib | timed_out | verdict |",
              "|---|---|---|---|---|---|---|---|---|"]
    for row in summary["rows"]:
        wall = round(row["wall_ms"]) if isinstance(row["wall_ms"], (int, float)) else None
        cells = [row["id"], row["active"], row["status"], row["utility"], row["tokens"], wall,
                 row["peak_rss_kib"], row["timed_out"], row["verdict"]]
        lines.append("| " + " | ".join(_cell(c) for c in cells) + " |")
    lines += ["", "## Failures", ""]
    failures = [r for r in summary["rows"] if r["problems"]]
    for row in failures:
        lines.append(f"- {row['id']}: " + "; ".join(row["problems"][:5])
                     + (f"; and {len(row['problems']) - 5} more" if len(row["problems"]) > 5 else ""))
    if not failures:
        lines.append("- none")
    large = summary["large"]
    lines += ["", "## Summary", "",
              "- status counts: " + ", ".join(f"{k}={v}" for k, v in sorted(summary["status_counts"].items())),
              f"- max wall_ms overall: {_cell(summary['max_wall_ms'])}",
              f"- valid feasible requests with at least {large['min_active']} active cards: n={large['n']}, "
              f"p95 wall_ms (nearest rank)={_cell(large['p95_wall_ms'])}, "
              f"max peak_rss_kib={_cell(large['max_peak_rss_kib'])}"]
    for cert in summary["certificates"]:
        lines.append(f"- certificate {cert['id']}: U={cert['U']}, s={cert['s']}, utility={cert['utility']}, "
                     f"100*U <= 105*utility*s: {cert['within_5_percent']}")
    if not summary["certificates"]:
        lines.append("- certificates: none present on a profile instance")
    for pair in summary["consistency_pairs"]:
        lines.append(f"- consistency {pair['ids'][0]} / {pair['ids'][1]}: L={_cell(pair['L'])}, H={_cell(pair['H'])}, "
                     f"200*(H-L) <= H: {_cell(pair['within_half_percent'])}")
    lines += ["", "## Environment", "", "```json",
              json.dumps(summary["environment"], ensure_ascii=False, indent=2, sort_keys=True), "```", "",
              f"RESULT: {'PASS' if summary['passed'] else 'FAIL'} "
              f"({len(summary['failed_ids'])} of {len(summary['rows'])} records failed, "
              f"{sum(1 for c in summary['integrity'] if not c['ok'])} integrity checks failed)"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check a recorded benchmark run.")
    parser.add_argument("dir", type=Path, help="directory holding benchmark_results.json and benchmark_inputs.json")
    parser.add_argument("--json", type=Path, dest="json_path", help="also write the summary as JSON here")
    parser.add_argument("--allow-wrong", action="store_true", help="print everything but exit 0 on failures")
    args = parser.parse_args(argv)
    inputs_path = args.dir / "benchmark_inputs.json"
    try:
        results = json.loads((args.dir / "benchmark_results.json").read_text(encoding="utf-8"))
        inputs_bytes = inputs_path.read_bytes()
    except (OSError, ValueError) as exc:
        print(f"check_results: {exc}", file=sys.stderr)
        return 1
    summary = evaluate(results, json.loads(inputs_bytes), load_checker())
    on_disk = hashlib.sha256(inputs_bytes).hexdigest()
    summary["integrity"].append({"check": "benchmark_inputs.json on disk matches the baseline",
                                 "ok": on_disk == INPUTS_SHA256, "detail": on_disk})
    summary["passed"] = summary["passed"] and on_disk == INPUTS_SHA256
    print(render(summary))
    if args.json_path is not None:
        args.json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if summary["passed"]:
        return 0
    if args.allow_wrong:
        print("check_results: failures present; exit code suppressed by --allow-wrong", file=sys.stderr)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
