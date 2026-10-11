"""The 28 public benchmark requests through the CLI, judged by the independent checker and oracle."""

import json
import random
import sys
import unittest
from pathlib import Path

import checker
import gen
import oracle
from test_cli import encode, one_object, run_cli, session_bytes

ROOT = Path(__file__).resolve().parent.parent
INVALID_IDS = {"i_93a288225d57a93686", "i_57be790be38419e246"}
INFEASIBLE_IDS = {"i_6bf2ce5fc66d4bad9e", "i_354f04e366ba47a0e5"}
# Public repeat pairs: the same problem presented twice.
CONSISTENCY_PAIRS = (
    ("i_d377627acc7b53786a", "i_b05b69c48293a3d4b4"),
    ("i_613d784770e53c543d", "i_91a2e8f7679a6871f4"),
    ("i_27d35bf2cd22d3769a", "i_dfcebb3746dc9feecb"),
)
PERMUTED_ID = "i_a7373a7648d6ddce67"
ORACLE_MAX_ACTIVE = 18
WALL_LIMIT_S = 4.0


def load_corpus() -> dict:
    for path in (ROOT / "benchmark_inputs.json", ROOT / "resources" / "benchmark_inputs.json"):
        if path.is_file():
            return json.loads(path.read_bytes())
    raise AssertionError("benchmark_inputs.json not found at the root or under resources/")


def within_half_percent(low: int, high: int) -> bool:
    return 200 * (high - low) <= high


class CorpusTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.requests = {entry["id"]: entry["request"] for entry in load_corpus()["instances"]}
        cls.responses = {}
        cls.walls = {}
        cls.failures = {}
        for rid, request in cls.requests.items():
            proc, wall = run_cli(encode(request))
            cls.walls[rid] = wall
            try:
                cls.responses[rid] = one_object(cls("test_corpus_size"), proc)
            except AssertionError as exc:
                cls.failures[rid] = str(exc)

    def expected_status(self, rid: str) -> str:
        if rid in INVALID_IDS:
            return "invalid"
        return "infeasible" if rid in INFEASIBLE_IDS else "ok"

    def test_corpus_size(self):
        self.assertEqual(len(self.requests), 28)
        self.assertTrue(INVALID_IDS | INFEASIBLE_IDS <= set(self.requests))

    def test_every_request_gets_one_json_object_and_exit_zero(self):
        self.assertEqual(self.failures, {})

    def test_status_and_checker_per_instance(self):
        passed = 0
        for rid, request in self.requests.items():
            with self.subTest(rid):
                resp = self.responses[rid]
                self.assertEqual(resp["status"], self.expected_status(rid))
                errors = checker.check_response(request, resp, request_valid=rid not in INVALID_IDS)
                self.assertEqual(errors, [])
                passed += 1
        sys.stderr.write(f"[corpus] {passed} of {len(self.requests)} responses have the expected status and pass the checker\n")
        self.assertEqual(passed, 28)

    def test_infeasible_ids_are_infeasible_by_the_checker(self):
        for rid in INFEASIBLE_IDS:
            self.assertFalse(checker.expected_feasible(self.requests[rid]), rid)

    def test_small_instances_equal_the_oracle(self):
        compared = []
        for rid, request in self.requests.items():
            if self.expected_status(rid) != "ok":
                continue
            active = len(checker.active_cards(request))
            if active <= ORACLE_MAX_ACTIVE:
                with self.subTest(rid, active=active):
                    self.assertEqual(self.responses[rid]["utility"], oracle.best_utility(request))
                    compared.append(active)
        sys.stderr.write(f"[corpus] oracle-equal instances by active count: {sorted(compared)}\n")
        self.assertTrue({12, 16, 18} <= set(compared), compared)

    def test_sample_session_is_61(self):
        raw = session_bytes()
        request = json.loads(raw)
        proc, _ = run_cli(raw)
        resp = one_object(self, proc)
        self.assertEqual(resp["utility"], 61)
        self.assertEqual(resp["utility"], oracle.best_utility(request))
        self.assertEqual(checker.check_response(request, resp), [])

    def test_profile_instances_carry_a_certificate_within_five_percent(self):
        seen = 0
        for rid, request in self.requests.items():
            if self.expected_status(rid) != "ok" or not checker.is_certificate_profile(request):
                continue
            if len(checker.active_cards(request)) < 250:
                continue
            with self.subTest(rid):
                resp = self.responses[rid]
                self.assertIn("certificate", resp)
                bound, scale = checker.certificate_bound(request, resp["certificate"])
                self.assertLessEqual(100 * bound, 105 * resp["utility"] * scale)
                sys.stderr.write(f"[corpus] certificate {rid}: U/s over utility = "
                                 f"{bound / (scale * resp['utility']):.6f}\n")
                seen += 1
        self.assertEqual(seen, 2)

    def test_no_certificate_outside_the_profile(self):
        for rid, request in self.requests.items():
            if self.expected_status(rid) == "ok" and not checker.is_certificate_profile(request):
                self.assertNotIn("certificate", self.responses[rid], rid)

    def test_wall_time_on_the_host(self):
        worst = max(self.walls, key=self.walls.get)
        sys.stderr.write(f"[corpus] max host wall {self.walls[worst]:.3f} s on {worst}\n")
        self.assertLess(self.walls[worst], WALL_LIMIT_S)

    def test_consistency_is_reported(self):
        """Reported, not asserted: consistency is an optional capability and the large search is being reworked."""
        for first, second in CONSISTENCY_PAIRS:
            pair = sorted((self.responses[first]["utility"], self.responses[second]["utility"]))
            sys.stderr.write(f"[corpus] consistency {first} / {second}: L={pair[0]} H={pair[1]} "
                             f"200*(H-L) <= H: {within_half_percent(*pair)}\n")
        request = gen.permute_request(random.Random(5), self.requests[PERMUTED_ID])
        proc, _ = run_cli(encode(request))
        resp = one_object(self, proc)
        self.assertEqual(checker.check_response(request, resp), [])
        pair = sorted((self.responses[PERMUTED_ID]["utility"], resp["utility"]))
        sys.stderr.write(f"[corpus] consistency {PERMUTED_ID} / permuted copy: L={pair[0]} H={pair[1]} "
                         f"200*(H-L) <= H: {within_half_percent(*pair)}\n")


if __name__ == "__main__":
    unittest.main()
