"""Measure `dcp_search.solve_large` on the public instances with at least 25 active cards.

Usage (from the package root):
    python3.11 tools/tune_search.py [--quick] [--jobs N]

Prints one row per instance: utility at search deadlines 0.3 s, 1.0 s and 2.0 s, the best of three
reference runs with different seeds (20 s each, 5 s with --quick), and the ratio of the 2.0 s
result to that best. Instances run in separate worker processes (--jobs, default 4).
"""

import argparse
import json
import multiprocessing
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import dcp_model  # noqa: E402
import dcp_search  # noqa: E402

MIN_ACTIVE = 25
DEADLINES = (0.3, 1.0, 2.0)
REFERENCE_SEEDS = (1, 2, 3)


def _utility(p, mask: int) -> int:
    return dcp_model.cover_weight(p, dcp_model.mask_cover(p, mask))


def _run(p, seconds: float, seed: int) -> int:
    mask = dcp_search.solve_large(p, time.perf_counter() + seconds, seed)
    if not dcp_model.is_legal(p, mask):
        raise AssertionError("illegal mask returned")
    return _utility(p, mask)


def measure(job: tuple) -> tuple:
    iid, request, ref_seconds = job
    p = dcp_model.build_problem(request)
    unit = set(p.feat_w) == {1}
    at = []
    moves = 0
    for seconds in DEADLINES:
        at.append(_run(p, seconds, dcp_search.DEFAULT_SEED))
        moves = dcp_search.LAST_STATS["moves"]
    ref = max(_run(p, ref_seconds, seed) for seed in REFERENCE_SEEDS)
    return iid, p.n, unit, at, ref, int(moves / DEADLINES[-1]), dcp_search.LAST_STATS["greedy_utility"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--quick", action="store_true", help="5 s reference runs instead of 20 s")
    parser.add_argument("--jobs", type=int, default=4, help="worker processes")
    args = parser.parse_args()
    ref_seconds = 5.0 if args.quick else 20.0

    path = os.path.join(ROOT, "resources", "benchmark_inputs.json")
    if not os.path.exists(path):
        path = os.path.join(ROOT, "benchmark_inputs.json")
    with open(path, encoding="utf-8") as fh:
        corpus = json.load(fh)

    jobs = []
    for inst in corpus["instances"]:
        try:
            p = dcp_model.build_problem(inst["request"])
        except Exception:  # invalid or infeasible public requests are not search inputs
            continue
        if p.n >= MIN_ACTIVE:
            jobs.append((inst["id"], inst["request"], ref_seconds))

    with multiprocessing.Pool(max(1, args.jobs)) as pool:
        rows = pool.map(measure, jobs, chunksize=1)

    print(f"reference: best of {len(REFERENCE_SEEDS)} runs of {ref_seconds:.0f} s; jobs={args.jobs}")
    print(f"{'id':<22} {'act':>4} {'unit':>4} {'greedy':>7} {'0.3s':>7} {'1.0s':>7} {'2.0s':>7} {'ref':>7} "
          f"{'2.0s/ref':>8} {'moves/s':>8}")
    worst = None
    for iid, n, unit, at, ref, mps, greedy in sorted(rows, key=lambda r: (not r[2], r[1], r[0])):
        ratio = at[2] / ref if ref else 1.0
        if worst is None or ratio < worst[0]:
            worst = (ratio, iid)
        flag = "" if 100 * at[2] >= 99 * ref else "  BELOW 99%"
        print(f"{iid:<22} {n:>4} {'yes' if unit else 'no':>4} {greedy:>7} {at[0]:>7} {at[1]:>7} {at[2]:>7} "
              f"{ref:>7} {ratio:>8.4f} {mps:>8}{flag}")
    if worst:
        print(f"worst 2.0s/ref ratio: {worst[0]:.4f} ({worst[1]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
