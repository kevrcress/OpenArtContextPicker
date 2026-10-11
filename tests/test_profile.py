"""Tests for dcp_profile: profile detection, exact knapsack and the utility upper-bound certificate."""

from __future__ import annotations

import json
import os
import random
import time
import unittest

import checker
import gen
import oracle

import dcp_model
import dcp_profile
from dcp_model import Infeasible, build_problem

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_UNIT_TOKEN_ID = "i_9e24f6f61fea4413ac"
_MIXED_TOKEN_ID = "i_cf46e9e6258788de2a"
_FAR = 3600.0  # seconds; a deadline no test reaches


def card(cid, tokens=1, covers=(), version="v0", supersedes=(), requires=(), group=None):
    """Build one card dict in the validated request shape."""
    return {
        "id": cid,
        "version": version,
        "supersedes": list(supersedes),
        "requires": list(requires),
        "conflict_group": group,
        "tokens": tokens,
        "covers": list(covers),
    }


def request(cards, features, budget, mandatory=(), contradictions=(), versions=None, head="v0"):
    """Build a request dict in the validated request shape."""
    return {
        "versions": versions or [{"id": "v0", "parents": []}],
        "cards": cards,
        "features": dict(features),
        "head": head,
        "budget": budget,
        "mandatory": list(mandatory),
        "contradictions": [list(pair) for pair in contradictions],
    }


def profile_request(rng, n_cards, n_mandatory=0, p_supersede=0.0):
    """A generated valid request in the certificate profile: distinct features per card."""
    req = gen.random_request(
        rng, n_cards, n_versions=rng.randint(1, 3), p_requires=0, p_group=0, n_pairs=0, p_supersede=p_supersede,
        n_features=3 * n_cards + 2, max_covers=0, budget_ratio=rng.choice((0.2, 0.5, 0.8)), n_mandatory=n_mandatory,
    )
    pool = sorted(req["features"])
    rng.shuffle(pool)
    for item in req["cards"]:
        item["covers"] = [pool.pop() for _ in range(rng.randint(0, 3))]
    return req


def solve(req, deadline=None):
    """Return ``(problem, mask)`` for ``req`` from the profile solver."""
    p = build_problem(req)
    limit = time.perf_counter() + _FAR if deadline is None else deadline
    return p, dcp_profile.solve_profile(p, limit)


def utility_of(p, mask):
    """Return the utility of ``mask``."""
    return dcp_model.cover_weight(p, dcp_model.mask_cover(p, mask))


def load_public(instance_id):
    """Return the public request with ``instance_id``; fails when the corpus is missing."""
    for name in ("benchmark_inputs.json", os.path.join("resources", "benchmark_inputs.json")):
        path = os.path.join(_ROOT, name)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as handle:
                corpus = json.load(handle)
            for instance in corpus["instances"]:
                if instance["id"] == instance_id:
                    return instance["request"]
            raise AssertionError(f"{instance_id} is not in {path}")
    raise AssertionError("benchmark_inputs.json was not found")


class ProfileAppliesTest(unittest.TestCase):
    def base(self):
        return [card("a", 2, ["fa"]), card("b", 3, ["fb"])], {"fa": 5, "fb": 7, "fz": 1}

    def applies(self, req):
        result = dcp_profile.profile_applies(req, build_problem(req))
        self.assertEqual(result, checker.is_certificate_profile(req))
        return result

    def test_plain_disjoint_request_applies(self):
        cards, features = self.base()
        self.assertTrue(self.applies(request(cards, features, 4)))

    def test_requires_group_or_pair_do_not_apply(self):
        cards, features = self.base()
        cards[0]["requires"] = ["b"]
        self.assertFalse(self.applies(request(cards, features, 4)))
        cards, features = self.base()
        cards[1]["conflict_group"] = "g"
        self.assertFalse(self.applies(request(cards, features, 4)))
        cards, features = self.base()
        self.assertFalse(self.applies(request(cards, features, 4, contradictions=[("a", "b")])))

    def test_group_on_an_invisible_card_does_not_apply(self):
        cards, features = self.base()
        cards.append(card("hidden", 1, ["fz"], version="v1", group="g"))
        versions = [{"id": "v0", "parents": []}, {"id": "v1", "parents": ["v0"]}]
        self.assertFalse(self.applies(request(cards, features, 4, versions=versions, head="v0")))

    def test_feature_shared_by_two_active_cards_does_not_apply(self):
        cards, features = self.base()
        cards[1]["covers"] = ["fb", "fa"]
        self.assertFalse(self.applies(request(cards, features, 4)))

    def test_feature_shared_with_a_superseded_card_applies(self):
        cards, features = self.base()
        cards.append(card("a2", 1, ["fa"], supersedes=["a"]))
        self.assertTrue(self.applies(request(cards, features, 4)))


class SolveProfileTest(unittest.TestCase):
    def check_against_oracle(self, req):
        try:
            p, mask = solve(req)
        except Infeasible:
            self.assertFalse(checker.expected_feasible(req))
            return False
        self.assertTrue(dcp_profile.profile_applies(req, p))
        self.assertIsNotNone(mask)
        self.assertTrue(dcp_model.is_legal(p, mask))
        self.assertEqual(checker.legality_errors(req, dcp_model.mask_ids(p, mask)), [])
        self.assertEqual(utility_of(p, mask), oracle.best_utility(req))
        return True

    def test_equals_oracle_on_generated_profile_requests(self):
        rng = random.Random(7001)
        solved = 0
        for trial in range(240):
            n_cards = rng.randint(1, 16)
            req = profile_request(
                rng, n_cards, n_mandatory=rng.choice((0, 0, 1, 2)) if trial % 2 else 0,
                p_supersede=0.3 if trial % 3 == 0 else 0.0,
            )
            with self.subTest(trial=trial):
                solved += self.check_against_oracle(req)
        self.assertGreater(solved, 150)

    def test_mandatory_card_is_forced(self):
        cards = [card("m", 6, ["fm"]), card("a", 5, ["fa"]), card("b", 5, ["fb"]), card("c", 4, ["fc"])]
        req = request(cards, {"fm": 1, "fa": 50, "fb": 40, "fc": 30}, 10, mandatory=["m"])
        p, mask = solve(req)
        self.assertEqual(dcp_model.mask_ids(p, mask), ["c", "m"])
        self.assertEqual(utility_of(p, mask), 31)
        self.assertEqual(utility_of(p, mask), oracle.best_utility(req))

    def test_superseded_card_is_never_selected(self):
        cards = [card("old", 1, ["fo"]), card("new", 4, ["fn"], supersedes=["old"]), card("x", 3, ["fx"])]
        req = request(cards, {"fo": 99, "fn": 5, "fx": 4}, 4)
        p, mask = solve(req)
        self.assertEqual(p.ids, ("new", "x"))
        self.assertEqual(dcp_model.mask_ids(p, mask), ["new"])
        self.assertEqual(utility_of(p, mask), oracle.best_utility(req))

    def test_zero_budget_and_no_cards_give_the_mandatory_set(self):
        req = request([card("a", 2, ["fa"])], {"fa": 5}, 0)
        p, mask = solve(req)
        self.assertEqual(mask, 0)
        req = request([], {"fa": 5}, 9)
        p, mask = solve(req)
        self.assertEqual(mask, 0)

    def test_past_deadline_returns_none(self):
        req = gen.max_request(random.Random(3), profile=True)
        _, mask = solve(req, deadline=time.perf_counter() - 1.0)
        self.assertIsNone(mask)

    def test_short_deadline_returns_none_or_a_legal_mask_in_time(self):
        req = gen.max_request(random.Random(4), profile=True)
        p = build_problem(req)
        start = time.perf_counter()
        mask = dcp_profile.solve_profile(p, start + 0.05)
        elapsed = time.perf_counter() - start
        self.assertLess(elapsed, 0.5)
        if mask is not None:
            self.assertTrue(dcp_model.is_legal(p, mask))

    def test_contract_maximum_finishes_under_the_limit(self):
        req = gen.max_request(random.Random(20261011), profile=True)
        p = build_problem(req)
        self.assertEqual((p.n, p.budget), (500, 8192))
        self.assertTrue(dcp_profile.profile_applies(req, p))
        start = time.perf_counter()
        mask = dcp_profile.solve_profile(p, start + 10.0)
        elapsed = time.perf_counter() - start
        print(f"contract-maximum profile: solve_profile {elapsed:.3f} s, solved={mask is not None}")
        self.assertIsNotNone(mask)
        self.assertLess(elapsed, 3.0)
        self.assertTrue(dcp_model.is_legal(p, mask))
        self.assertLessEqual(dcp_model.mask_tokens(p, mask), p.budget)
        response = checker.response_for(req, dcp_model.mask_ids(p, mask))
        certificate = dcp_profile.build_certificate(p, mask)
        if certificate is not None:
            response["certificate"] = certificate
        self.assertEqual(checker.check_response(req, response), [])


class CertificateTest(unittest.TestCase):
    def assert_tight(self, req, p, mask):
        """Assert a certificate exists, passes the checker and meets the 5% gap; return ``(U, s, utility)``."""
        certificate = dcp_profile.build_certificate(p, mask)
        self.assertIsNotNone(certificate)
        self.assertEqual(set(certificate), {"scale", "budget_price", "feature_prices"})
        self.assertEqual(set(certificate["feature_prices"]), set(req["features"]))
        response = checker.response_for(req, dcp_model.mask_ids(p, mask))
        response["certificate"] = certificate
        self.assertEqual(checker.check_response(req, response), [])
        bound, scale = checker.certificate_bound(req, certificate)
        utility = response["utility"]
        self.assertGreaterEqual(bound, utility * scale)
        self.assertLessEqual(100 * bound, 105 * utility * scale)
        return bound, scale, utility

    def test_exact_fill_gives_a_zero_gap_certificate(self):
        cards = [card("a", 2, ["fa"]), card("b", 3, ["fb"]), card("c", 5, ["fc"])]
        req = request(cards, {"fa": 20, "fb": 24, "fc": 10, "unused": 7}, 5)
        p, mask = solve(req)
        bound, scale, utility = self.assert_tight(req, p, mask)
        self.assertEqual(utility, 44)
        self.assertEqual(bound, utility * scale)

    def test_everything_fits_uses_a_zero_budget_price(self):
        cards = [card("a", 2, ["fa"]), card("b", 3, ["fb"])]
        req = request(cards, {"fa": 20, "fb": 24}, 50)
        p, mask = solve(req)
        certificate = dcp_profile.build_certificate(p, mask)
        self.assertEqual((certificate["scale"], certificate["budget_price"]), (1, 0))
        self.assert_tight(req, p, mask)

    def test_loose_relaxation_returns_none(self):
        cards = [card("a", 6, ["fa"]), card("b", 6, ["fb"])]
        req = request(cards, {"fa": 10, "fb": 10}, 10)
        p, mask = solve(req)
        self.assertEqual(utility_of(p, mask), 10)
        self.assertIsNone(dcp_profile.build_certificate(p, mask))

    def test_poor_mandatory_card_returns_none(self):
        cards = [card("m", 9, ["fm"]), card("a", 5, ["fa"]), card("b", 5, ["fb"])]
        req = request(cards, {"fm": 1, "fa": 50, "fb": 50}, 10, mandatory=["m"])
        p, mask = solve(req)
        self.assertEqual(dcp_model.mask_ids(p, mask), ["m"])
        self.assertIsNone(dcp_profile.build_certificate(p, mask))

    def test_suboptimal_mask_returns_none(self):
        cards = [card("a", 2, ["fa"]), card("b", 3, ["fb"])]
        req = request(cards, {"fa": 20, "fb": 24}, 5)
        p = build_problem(req)
        self.assertIsNone(dcp_profile.build_certificate(p, 0))
        self.assertIsNone(dcp_profile.build_certificate(p, 1))

    def test_returned_certificates_are_always_valid_bounds(self):
        rng = random.Random(7002)
        returned = 0
        for trial in range(200):
            req = profile_request(rng, rng.randint(1, 16), p_supersede=0.2 if trial % 2 else 0.0)
            p, mask = solve(req)
            certificate = dcp_profile.build_certificate(p, mask)
            if certificate is None:
                continue
            returned += 1
            with self.subTest(trial=trial):
                self.assertEqual(checker.certificate_errors(req, certificate), [])
                bound, scale = checker.certificate_bound(req, certificate)
                best = oracle.best_utility(req)
                self.assertGreaterEqual(bound, best * scale)
                self.assertLessEqual(100 * bound, 105 * utility_of(p, mask) * scale)
        self.assertGreater(returned, 20)

    def test_certificate_on_a_non_profile_request_is_still_a_valid_bound(self):
        rng = random.Random(7003)
        for trial in range(60):
            req = gen.random_request(rng, rng.randint(2, 12))
            try:
                p = build_problem(req)
            except Infeasible:
                continue
            certificate = dcp_profile.build_certificate(p, p.mandatory)
            if certificate is None:
                continue
            with self.subTest(trial=trial):
                self.assertEqual(checker.certificate_errors(req, certificate), [])
                bound, scale = checker.certificate_bound(req, certificate)
                self.assertGreaterEqual(bound, oracle.best_utility(req) * scale)

    def public_instance(self, instance_id):
        req = load_public(instance_id)
        p = build_problem(req)
        self.assertTrue(checker.is_certificate_profile(req))
        self.assertTrue(dcp_profile.profile_applies(req, p))
        start = time.perf_counter()
        mask = dcp_profile.solve_profile(p, start + _FAR)
        elapsed = time.perf_counter() - start
        self.assertTrue(dcp_model.is_legal(p, mask))
        bound, scale, utility = self.assert_tight(req, p, mask)
        print(
            f"{instance_id}: active={p.n} budget={p.budget} utility={utility} tokens={dcp_model.mask_tokens(p, mask)} "
            f"U={bound} scale={scale} 100*U={100 * bound} 105*utility*scale={105 * utility * scale} "
            f"solve={elapsed:.3f} s"
        )
        return req, p, mask, utility

    def test_public_unit_token_instance(self):
        req, p, mask, utility = self.public_instance(_UNIT_TOKEN_ID)
        self.assertEqual((p.n, p.budget), (256, 93))
        values = sorted((sum(req["features"][f] for f in c["covers"]) for c in req["cards"]), reverse=True)
        self.assertEqual(utility, sum(values[:93]))

    def test_public_mixed_token_instance(self):
        _, p, _, _ = self.public_instance(_MIXED_TOKEN_ID)
        self.assertEqual((p.n, p.budget), (320, 2571))


class ModuleBoundaryTest(unittest.TestCase):
    def test_profile_module_imports_only_the_model(self):
        with open(os.path.join(_ROOT, "dcp_profile.py"), encoding="utf-8") as handle:
            source = handle.read()
        self.assertNotIn("dcp_search", source)
        self.assertNotIn("dcp_exact", source)


if __name__ == "__main__":
    unittest.main()
