"""Tests for dcp_search.solve_large: legality, quality against the oracle, deadline and seed interface."""

import json
import os
import random
import time
import unittest

import checker
import gen
import oracle

import dcp_model
import dcp_search

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIN_ACTIVE = 25
LATE_ALLOWANCE_S = 0.05


def _corpus_path() -> str:
    for candidate in (os.path.join(ROOT, "benchmark_inputs.json"), os.path.join(ROOT, "resources", "benchmark_inputs.json")):
        if os.path.exists(candidate):
            return candidate
    return ""


def _utility(p, mask: int) -> int:
    return dcp_model.cover_weight(p, dcp_model.mask_cover(p, mask))


def _solve(p, seconds: float, seed: int = dcp_search.DEFAULT_SEED) -> tuple:
    deadline = time.perf_counter() + seconds
    mask = dcp_search.solve_large(p, deadline, seed)
    return mask, time.perf_counter() - deadline


class GeneratedRequestsTest(unittest.TestCase):
    def test_given_small_generated_requests_when_solved_then_legal_and_near_oracle(self):
        rng = random.Random(6001)
        checked = 0
        within = 0
        for k in range(35):
            n_cards = 10 + k % 7
            request = gen.random_request(rng, n_cards, n_pairs=rng.randint(0, 2 * n_cards), n_mandatory=k % 2,
                                         budget_ratio=rng.choice((0.3, 0.5, 0.7)))
            try:
                p = dcp_model.build_problem(request)
            except dcp_model.Infeasible:
                continue
            mask, _ = _solve(p, 0.08, seed=k)
            self.assertTrue(dcp_model.is_legal(p, mask), f"case {k}")
            response = checker.response_for(request, dcp_model.mask_ids(p, mask))
            self.assertEqual(checker.check_response(request, response), [], f"case {k}")
            best = oracle.best_utility(request)
            self.assertLessEqual(response["utility"], best, f"case {k}")
            checked += 1
            if 100 * response["utility"] >= 99 * best:
                within += 1
        self.assertGreaterEqual(checked, 20)
        self.assertGreaterEqual(100 * within, 95 * checked, f"{within} of {checked} within 1% of the oracle")

    def test_given_requires_chains_when_solved_then_legal(self):
        rng = random.Random(6002)
        for k in range(12):
            request = gen.random_request(rng, 40, p_requires=0.7, p_group=0.5, n_pairs=60, n_mandatory=k % 3,
                                         n_versions=3, p_supersede=0.1)
            try:
                p = dcp_model.build_problem(request)
            except dcp_model.Infeasible:
                continue
            mask, _ = _solve(p, 0.05, seed=k)
            self.assertTrue(dcp_model.is_legal(p, mask), f"case {k}")
            self.assertEqual(mask & p.mandatory, p.mandatory)
            response = checker.response_for(request, dcp_model.mask_ids(p, mask))
            self.assertEqual(checker.check_response(request, response), [], f"case {k}")


class PublicInstancesTest(unittest.TestCase):
    def test_given_public_instances_of_25_or_more_active_cards_when_solved_then_checker_accepts(self):
        path = _corpus_path()
        self.assertTrue(path, "benchmark_inputs.json not found in the package root or resources/")
        with open(path, encoding="utf-8") as fh:
            corpus = json.load(fh)
        checked = 0
        for inst in corpus["instances"]:
            request = inst["request"]
            try:
                p = dcp_model.build_problem(request)
            except Exception:  # invalid and infeasible public requests are not search inputs
                continue
            if p.n < MIN_ACTIVE:
                continue
            mask, late = _solve(p, 0.25)
            self.assertLess(late, LATE_ALLOWANCE_S, inst["id"])
            self.assertTrue(dcp_model.is_legal(p, mask), inst["id"])
            response = checker.response_for(request, dcp_model.mask_ids(p, mask))
            self.assertEqual(checker.check_response(request, response), [], inst["id"])
            self.assertGreaterEqual(_utility(p, mask), _utility(p, p.mandatory), inst["id"])
            checked += 1
        self.assertGreaterEqual(checked, 16)


class DeadlineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.request = gen.max_request(random.Random(6003))
        cls.problem = dcp_model.build_problem(cls.request)

    def test_given_contract_maximum_request_when_deadline_passes_then_returns_within_50_ms(self):
        for seconds in (0.02, 0.2, 0.6):
            mask, late = _solve(self.problem, seconds)
            self.assertLess(late, LATE_ALLOWANCE_S, f"deadline {seconds}")
            self.assertTrue(dcp_model.is_legal(self.problem, mask))
            response = checker.response_for(self.request, dcp_model.mask_ids(self.problem, mask))
            self.assertEqual(checker.check_response(self.request, response), [])

    def test_given_deadline_in_the_past_when_solved_then_returns_mandatory_closure_at_once(self):
        start = time.perf_counter()
        mask = dcp_search.solve_large(self.problem, start - 1.0)
        self.assertLess(time.perf_counter() - start, LATE_ALLOWANCE_S)
        self.assertTrue(dcp_model.is_legal(self.problem, mask))
        self.assertEqual(mask & self.problem.mandatory, self.problem.mandatory)


class SeedInterfaceTest(unittest.TestCase):
    def setUp(self):
        self.request = gen.random_request(random.Random(6004), 60, n_pairs=150, budget_ratio=0.3)
        self.problem = dcp_model.build_problem(self.request)

    def test_given_default_seed_when_inspected_then_it_is_the_documented_value(self):
        self.assertEqual(dcp_search.DEFAULT_SEED, 20261011)

    def test_given_different_seeds_when_solved_then_each_result_is_legal(self):
        for seed in (0, 1, 20261011):
            mask, _ = _solve(self.problem, 0.05, seed=seed)
            self.assertTrue(dcp_model.is_legal(self.problem, mask), f"seed {seed}")

    def test_given_global_random_state_when_solved_then_it_is_untouched(self):
        random.seed(77)
        expected = random.random()
        random.seed(77)
        _solve(self.problem, 0.05)
        self.assertEqual(random.random(), expected)

    def test_given_search_time_when_solved_then_not_worse_than_greedy(self):
        mask, _ = _solve(self.problem, 0.2)
        self.assertGreaterEqual(_utility(self.problem, mask), dcp_search.LAST_STATS["greedy_utility"])


class FallbackTest(unittest.TestCase):
    def test_given_no_cards_fit_when_solved_then_returns_mandatory(self):
        request = gen.random_request(random.Random(6005), 30, n_pairs=20)
        request["budget"] = 0
        try:
            p = dcp_model.build_problem(request)
        except dcp_model.Infeasible:
            self.skipTest("generated request has zero-budget mandatory cards")
        mask, _ = _solve(p, 0.05)
        self.assertTrue(dcp_model.is_legal(p, mask))
        self.assertEqual(dcp_model.mask_tokens(p, mask), 0)


if __name__ == "__main__":
    unittest.main()
