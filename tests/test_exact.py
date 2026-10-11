"""Tests for dcp_exact.solve_exact: oracle agreement, 24-card stress families and deadline behaviour."""

from __future__ import annotations

import copy
import json
import os
import random
import time
import unittest

import dcp_model
import gen
import oracle
from dcp_exact import solve_exact

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PUBLIC_SMALL = ("i_658192e99b3806aff2", "i_299ba50f55c486ec71", "i_6421fda8c234f4ca23")
_LIMIT_24 = 1.5


def _request(cards, features, budget, pairs=(), mandatory=()):
    return {
        "versions": [{"id": "v0", "parents": []}],
        "cards": cards,
        "features": features,
        "head": "v0",
        "budget": budget,
        "mandatory": list(mandatory),
        "contradictions": [list(pair) for pair in pairs],
    }


def _card(i, tokens, covers, requires=(), group=None):
    return {"id": f"c{i:02d}", "version": "v0", "supersedes": [], "requires": [f"c{j:02d}" for j in requires],
            "conflict_group": group, "tokens": tokens, "covers": [f"f{k}" for k in covers]}


def _budget(cards, ratio):
    return int(ratio * sum(c["tokens"] for c in cards))


def shared_loose(rng, n, ratio=0.8):
    """Unconstrained cards, heavily shared features."""
    n_feat = n + 8
    features = {f"f{k}": rng.randint(1, 100) for k in range(n_feat)}
    cards = [_card(i, rng.randint(1, 60), rng.sample(range(n_feat), rng.randint(4, 14))) for i in range(n)]
    return _request(cards, features, _budget(cards, ratio))


def knapsack(rng, n, mode="uncorrelated", ratio=0.5):
    """One private feature per card: a plain 0/1 knapsack."""
    cards = []
    features = {}
    for i in range(n):
        tokens = rng.randint(20, 512)
        if mode == "uncorrelated":
            value = rng.randint(1, 1000)
        elif mode == "strong":
            value = tokens + 50
        else:  # subset sum
            value = tokens
        features[f"f{i}"] = value
        cards.append(_card(i, tokens, [i]))
    return _request(cards, features, _budget(cards, ratio))


def conflict_dense(rng, n, density=0.4):
    """Dense contradiction graph over cards with shared features."""
    n_feat = 2 * n
    features = {f"f{k}": rng.randint(1, 100) for k in range(n_feat)}
    cards = [_card(i, rng.randint(1, 40), rng.sample(range(n_feat), rng.randint(2, 8))) for i in range(n)]
    pairs = [(f"c{i:02d}", f"c{j:02d}") for i in range(n) for j in range(i + 1, n) if rng.random() < density]
    return _request(cards, features, _budget(cards, rng.choice((0.4, 0.7, 1.0))), pairs)


def chains(rng, n, cycle=False):
    """Long requirement chains; with ``cycle`` the last card of a chain requires the first."""
    n_feat = n + 4
    features = {f"f{k}": rng.randint(1, 100) for k in range(n_feat)}
    length = rng.choice((4, 6, 8, n))
    cards = []
    for i in range(n):
        requires = [i - 1] if i % length else []
        if cycle and i % length == 0 and i + length - 1 < n and rng.random() < 0.5:
            requires = [i + length - 1]
        cards.append(_card(i, rng.randint(1, 40), rng.sample(range(n_feat), rng.randint(0, 4)), requires))
    pairs = [(f"c{rng.randrange(n):02d}", f"c{rng.randrange(n):02d}") for _ in range(3)]
    pairs = [pair for pair in pairs if pair[0] != pair[1]]
    return _request(cards, features, _budget(cards, rng.choice((0.3, 0.5, 0.8))), pairs)


def one_group(rng, n):
    """Most cards share one conflict group; the rest are free."""
    n_feat = n + 6
    features = {f"f{k}": rng.randint(1, 100) for k in range(n_feat)}
    in_group = rng.choice((n, n - 4, n // 2))
    cards = [_card(i, rng.randint(1, 40), rng.sample(range(n_feat), rng.randint(1, 8)),
                   group="g0" if i < in_group else None) for i in range(n)]
    return _request(cards, features, _budget(cards, rng.choice((0.2, 0.5))))


def k_cover(rng, n, n_feat=200, low=30, high=64, ratio=0.4):
    """Equal-token cards with wide covers: a budgeted maximum-coverage problem."""
    features = {f"f{k}": rng.randint(1, 100) for k in range(n_feat)}
    cards = [_card(i, 10, rng.sample(range(n_feat), rng.randint(low, high))) for i in range(n)]
    return _request(cards, features, _budget(cards, ratio))


def independent_set(rng, n, degree=1):
    """Private near-equal features, sparse contradictions, no budget pressure."""
    features = {f"f{i}": rng.randint(90, 110) for i in range(n)}
    cards = [_card(i, rng.randint(1, 40), [i]) for i in range(n)]
    pairs = set()
    for i in range(n):
        for _ in range(degree):
            j = rng.randrange(n)
            if j != i:
                pairs.add((min(i, j), max(i, j)))
    return _request(cards, features, 10 ** 6, [(f"c{a:02d}", f"c{b:02d}") for a, b in sorted(pairs)])


def mixture(rng, n):
    return gen.random_request(rng, n, p_requires=rng.choice((0.0, 0.2, 0.5)), p_group=rng.choice((0.0, 0.3)),
                              n_pairs=rng.choice((0, n // 2, 2 * n)), n_features=rng.choice((n // 2 + 1, n, 3 * n)),
                              max_covers=rng.choice((3, 8, 16)), max_tokens=rng.choice((8, 40, 512)),
                              budget_ratio=rng.choice((0.2, 0.5, 0.8)))


FAMILIES = {
    "shared-loose": lambda rng, n: shared_loose(rng, n, 0.8),
    "shared-mid": lambda rng, n: shared_loose(rng, n, 0.45),
    "shared-tight": lambda rng, n: shared_loose(rng, n, 0.2),
    "knapsack-uncorrelated": lambda rng, n: knapsack(rng, n, "uncorrelated"),
    "knapsack-strong": lambda rng, n: knapsack(rng, n, "strong"),
    "knapsack-subset-sum": lambda rng, n: knapsack(rng, n, "subset"),
    "conflict-dense": conflict_dense,
    "conflict-sparse": lambda rng, n: conflict_dense(rng, n, 0.12),
    "chains": chains,
    "cycles": lambda rng, n: chains(rng, n, cycle=True),
    "one-group": one_group,
    "mixture": mixture,
    "k-cover-wide": lambda rng, n: k_cover(rng, n, 1000, 40, 64, 0.4),
    "k-cover-quarter": lambda rng, n: k_cover(rng, n, 200, 30, 64, 0.25),
    "independent-set-1": lambda rng, n: independent_set(rng, n, 1),
    "independent-set-2": lambda rng, n: independent_set(rng, n, 2),
}


def _utility(p, mask):
    return dcp_model.cover_weight(p, dcp_model.mask_cover(p, mask))


def _solve(request, seconds=30.0):
    p = dcp_model.build_problem(request)
    start = time.perf_counter()
    mask, proven = solve_exact(p, start + seconds)
    return p, mask, proven, time.perf_counter() - start


def _knapsack_optimum(request):
    """Independent dynamic programme for the private-feature knapsack families."""
    table = [0] * (request["budget"] + 1)
    for c in request["cards"]:
        tokens, value = c["tokens"], request["features"][c["covers"][0]]
        for room in range(request["budget"], tokens - 1, -1):
            if table[room - tokens] + value > table[room]:
                table[room] = table[room - tokens] + value
    return table[request["budget"]]


def _padded_to_24(rng, n_core):
    """Return ``(core, full)``: a constrained core request and a 24-card request with the same optimum.

    Why the optimum is preserved. ``full`` is ``core`` plus filler cards, with
    every core card, feature weight, pair and the budget left unchanged. No
    card requires a filler and no filler is mandatory, so removing every filler
    from a legal set of ``full`` leaves a legal set: dropping cards cannot
    break the budget, a conflict group, a contradiction or another card's
    requirements. That set uses core cards only, so it is legal in ``core``.
    It also has the same utility, because a filler is one of two kinds:
    a free filler covers nothing, and an oversize filler costs more tokens
    than the budget and so is in no legal set at all. Conversely every legal
    set of ``core`` is legal in ``full``. The two maxima are therefore equal,
    and ``core`` is small enough for the exhaustive oracle.
    """
    core = gen.random_request(rng, n_core, p_requires=rng.choice((0.2, 0.4)), p_group=rng.choice((0.0, 0.3)),
                              n_pairs=rng.choice((n_core // 2, n_core)), n_features=2 * n_core,
                              max_covers=rng.choice((3, 6)), max_tokens=40, budget_ratio=rng.choice((0.3, 0.5, 0.7)))
    full = copy.deepcopy(core)
    core_ids = [c["id"] for c in core["cards"]]
    feature_ids = sorted(core["features"])
    version = core["head"]
    for j in range(24 - n_core):
        filler = {"id": f"pad{j:02d}", "version": version, "supersedes": [], "conflict_group": None}
        assert filler["id"] not in core_ids
        if j % 2 and core["budget"] < 512:
            # Oversize: tempting covers, but it can never fit.
            filler.update(tokens=rng.randint(core["budget"] + 1, 512), requires=[],
                          covers=rng.sample(feature_ids, rng.randint(1, 6)))
        else:
            # Free: covers nothing; may itself require a core card and contradict one.
            filler.update(tokens=rng.randint(1, 40), requires=rng.sample(core_ids, rng.randint(0, 1)), covers=[])
            if rng.random() < 0.5:
                full["contradictions"].append([filler["id"], rng.choice(core_ids)])
        full["cards"].append(filler)
    rng.shuffle(full["cards"])
    return core, full


class OracleAgreementTest(unittest.TestCase):
    def _compare(self, request, label):
        """Return True when a comparison was made, False when both sides call the request infeasible."""
        try:
            p = dcp_model.build_problem(request)
        except dcp_model.Infeasible:
            with self.assertRaises(LookupError, msg=label):
                oracle.best_utility(request)
            return False
        expected = oracle.best_utility(request)
        mask, proven = solve_exact(p, time.perf_counter() + 30.0)
        self.assertTrue(proven, label)
        self.assertTrue(dcp_model.is_legal(p, mask), label)
        self.assertEqual(_utility(p, mask), expected, label)
        return True

    def test_generated_requests_up_to_16_active(self):
        rng = random.Random(5150)
        compared = 0
        for case in range(420):
            n = rng.randint(1, 16)
            request = gen.random_request(
                rng, n, n_versions=rng.choice((1, 1, 3, 6)), p_requires=rng.choice((0.0, 0.3, 0.6)),
                p_group=rng.choice((0.0, 0.3, 0.8)), n_pairs=rng.choice((0, n // 2, 2 * n)),
                p_supersede=rng.choice((0.0, 0.0, 0.3)), n_features=rng.choice((None, 3, 2 * n + 1)),
                max_covers=rng.choice((2, 5, 12)), max_tokens=rng.choice((5, 40, 300)),
                budget_ratio=rng.choice((0.0, 0.25, 0.5, 0.9, 1.0)), n_mandatory=rng.choice((0, 0, 0, 1, 2)))
            compared += self._compare(request, f"generated case {case}")
        self.assertGreaterEqual(compared, 300)

    def test_every_family_at_10_to_16_active(self):
        rng = random.Random(77)
        for name, build in FAMILIES.items():
            for case in range(8):
                n = rng.randint(10, 16)
                self.assertTrue(self._compare(build(rng, n), f"{name} n={n} case {case}"))

    def test_families_at_18_and_20_active(self):
        rng = random.Random(1820)
        for name, n in (("shared-mid", 18), ("knapsack-strong", 18), ("conflict-sparse", 18), ("cycles", 18),
                        ("mixture", 18), ("shared-tight", 20), ("knapsack-subset-sum", 20)):
            self.assertTrue(self._compare(FAMILIES[name](rng, n), f"{name} n={n}"))

    def test_public_small_instances(self):
        path = next((c for c in (os.path.join(_ROOT, "benchmark_inputs.json"),
                                 os.path.join(_ROOT, "resources", "benchmark_inputs.json")) if os.path.exists(c)), None)
        self.assertIsNotNone(path, "benchmark_inputs.json not found")
        with open(path, encoding="utf-8") as handle:
            instances = {inst["id"]: inst["request"] for inst in json.load(handle)["instances"]}
        for instance_id in _PUBLIC_SMALL:
            self.assertTrue(self._compare(instances[instance_id], instance_id))

    def test_sample_session(self):
        with open(os.path.join(_ROOT, "resources", "director_session.json"), encoding="utf-8") as handle:
            session = json.load(handle)
        request = session.get("request", session)
        self.assertTrue(self._compare(request, "director_session.json"))


class Stress24Test(unittest.TestCase):
    def test_24_active_cards_finish_proven_within_limit(self):
        rng = random.Random(2424)
        worst = (0.0, "")
        cases = 0
        for name, build in FAMILIES.items():
            for case in range(5):
                request = build(rng, 24)
                p, mask, proven, elapsed = _solve(request)
                label = f"{name} case {case}"
                self.assertEqual(p.n, 24, label)
                self.assertTrue(proven, label)
                self.assertTrue(dcp_model.is_legal(p, mask), label)
                self.assertLess(elapsed, _LIMIT_24, label)
                worst = max(worst, (elapsed, label))
                cases += 1
                if name.startswith("knapsack"):
                    self.assertEqual(_utility(p, mask), _knapsack_optimum(request), label)
                if case < 2:
                    # A renamed copy changes the bit order and so the search order.
                    q, other, proven_other, _ = _solve(gen.permute_request(rng, request))
                    self.assertTrue(proven_other, label)
                    self.assertEqual(_utility(q, other), _utility(p, mask), label)
        self.assertEqual(cases, 5 * len(FAMILIES))
        self.assertEqual(cases, 80)
        print(f"\nworst 24-card time: {worst[0]:.3f} s ({worst[1]}) over {cases} cases")

    def test_24_cards_reviewer_case_has_utility_4(self):
        # a alone fills the budget for weight 3; b and c together fit for weight 4.
        named = [("a", 2, ["x"]), ("b", 1, ["y"]), ("c", 1, ["z"])]
        named += [(f"n{i:02d}", 1, []) for i in range(21)]
        cards = [{"id": cid, "version": "v0", "supersedes": [], "requires": [], "conflict_group": None,
                  "tokens": tokens, "covers": covers} for cid, tokens, covers in named]
        request = _request(cards, {"x": 3, "y": 2, "z": 2}, 2)
        p, mask, proven, _ = _solve(request)
        self.assertEqual(p.n, 24)
        self.assertTrue(dcp_model.is_legal(p, mask))
        self.assertEqual(_utility(p, mask), 4)
        self.assertTrue(proven)

    def test_24_cards_with_a_reduced_core_match_the_oracle(self):
        rng = random.Random(1224)
        cases = 0
        for case in range(24):
            core, full = _padded_to_24(rng, rng.randint(12, 14))
            label = f"reduced-core case {case} core={len(core['cards'])}"
            expected = oracle.best_utility(core)
            p, mask, proven, elapsed = _solve(full)
            self.assertEqual(p.n, 24, label)
            self.assertTrue(dcp_model.is_legal(p, mask), label)
            self.assertEqual(_utility(p, mask), expected, label)
            self.assertTrue(proven, label)
            self.assertLess(elapsed, _LIMIT_24, label)
            cases += 1
        self.assertEqual(cases, 24)

    def test_hard_families_at_20_active_match_oracle(self):
        rng = random.Random(404)
        for name in ("k-cover-wide", "independent-set-1"):
            request = FAMILIES[name](rng, 20)
            p, mask, proven, _ = _solve(request)
            self.assertTrue(proven, name)
            self.assertEqual(_utility(p, mask), oracle.best_utility(request), name)


class ContractTest(unittest.TestCase):
    def test_no_usable_cards_returns_mandatory(self):
        request = _request([_card(0, 5, [0]), _card(1, 9, [1])], {"f0": 3, "f1": 4}, 5, mandatory=["c00"])
        p = dcp_model.build_problem(request)
        mask, proven = solve_exact(p, time.perf_counter() + 1.0)
        self.assertTrue(proven)
        self.assertEqual(mask, p.mandatory)

    def test_illegal_incumbent_is_ignored_and_legal_one_is_kept(self):
        rng = random.Random(9)
        request = shared_loose(rng, 12, 0.4)
        p = dcp_model.build_problem(request)
        full = (1 << len(p.ids)) - 1
        self.assertFalse(dcp_model.is_legal(p, full))
        mask, proven = solve_exact(p, time.perf_counter() + 5.0, incumbent=full)
        self.assertTrue(proven)
        self.assertEqual(_utility(p, mask), oracle.best_utility(request))
        again, proven = solve_exact(p, time.perf_counter() + 5.0, incumbent=mask)
        self.assertTrue(proven)
        self.assertEqual(_utility(p, again), _utility(p, mask))

    def test_expired_deadline_returns_a_legal_set_promptly(self):
        rng = random.Random(64)
        for n, mandatory in ((64, 0), (300, 0), (500, 0)):
            request = gen.random_request(rng, n, p_requires=0.1, p_group=0.1, n_pairs=n, n_features=2 * n,
                                         max_covers=24, max_tokens=512, budget_ratio=0.3, n_mandatory=mandatory)
            p = dcp_model.build_problem(request)
            incumbent = p.mandatory
            start = time.perf_counter()
            mask, proven = solve_exact(p, start + 0.05, incumbent=incumbent)
            elapsed = time.perf_counter() - start
            self.assertTrue(dcp_model.is_legal(p, mask), n)
            self.assertGreaterEqual(_utility(p, mask), _utility(p, incumbent), n)
            self.assertLess(elapsed, 0.25, f"n={n} proven={proven}")

    def test_already_expired_deadline_on_one_card_is_legal_and_unproven(self):
        card = {"id": "a", "version": "v0", "supersedes": [], "requires": [], "conflict_group": None,
                "tokens": 1, "covers": ["x"]}
        p = dcp_model.build_problem(_request([card], {"x": 1}, 1))
        mask, proven = solve_exact(p, time.perf_counter() - 1.0)
        self.assertTrue(dcp_model.is_legal(p, mask))
        self.assertFalse(proven)

    def test_already_expired_deadline_keeps_a_legal_incumbent_and_is_unproven(self):
        rng = random.Random(2401)
        request = shared_loose(rng, 24, 0.45)
        p = dcp_model.build_problem(request)
        incumbent, used = 0, 0
        for i in range(p.n):
            if used + p.tokens[i] <= p.budget:
                incumbent |= 1 << i
                used += p.tokens[i]
        self.assertTrue(dcp_model.is_legal(p, incumbent))
        self.assertGreater(_utility(p, incumbent), 0)
        mask, proven = solve_exact(p, time.perf_counter() - 1.0, incumbent=incumbent)
        self.assertTrue(dcp_model.is_legal(p, mask))
        self.assertGreaterEqual(_utility(p, mask), _utility(p, incumbent))
        self.assertFalse(proven)

    def test_deep_requirement_chain_needs_no_recursion(self):
        n = 400
        cards = [_card(i, 1, [i], [i - 1] if i else []) for i in range(n)]
        for i, c in enumerate(cards):
            c["id"] = f"c{i:03d}"
            c["requires"] = [f"c{i - 1:03d}"] if i else []
        request = _request(cards, {f"f{i}": 1 + i % 3 for i in range(n)}, 250)
        p = dcp_model.build_problem(request)
        mask, proven = solve_exact(p, time.perf_counter() + 5.0)
        self.assertTrue(proven)
        self.assertEqual(mask, (1 << 250) - 1)


if __name__ == "__main__":
    unittest.main()
