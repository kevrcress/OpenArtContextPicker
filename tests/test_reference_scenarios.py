"""The owner's reference scenarios, run through the CLI as a second, independent oracle."""

import json
import unittest
from pathlib import Path

import checker
from test_cli import one_object, run_cli

ROOT = Path(__file__).resolve().parent.parent
COPY = Path(__file__).resolve().parent / "data" / "reference_scenarios.json"
SOURCE = ROOT / "docs" / "reference-scenarios" / "scenarios.json"
EXPECTED_COUNTS = {"ok": 38, "infeasible": 8, "invalid": 56}


class ReferenceScenariosTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scenarios = json.loads(COPY.read_bytes())["scenarios"]

    def test_copy_matches_the_source_of_truth(self):
        if SOURCE.is_file():  # absent in the shipped package, where only the copy exists
            self.assertEqual(COPY.read_bytes(), SOURCE.read_bytes())

    def test_scenario_census(self):
        counts = {}
        for scenario in self.scenarios:
            status = scenario["expect"]["status"]
            counts[status] = counts.get(status, 0) + 1
        self.assertEqual(counts, EXPECTED_COUNTS)
        self.assertEqual(sum("raw_stdin" in s for s in self.scenarios), 10)
        self.assertEqual(len({s["id"] for s in self.scenarios}), 102)

    def test_every_scenario_through_the_cli(self):
        ran = {"ok": 0, "infeasible": 0, "invalid": 0}
        raw_ran = 0
        for scenario in self.scenarios:
            expect = scenario["expect"]
            with self.subTest(scenario["id"]):
                if "raw_stdin" in scenario:
                    raw = scenario["raw_stdin"].encode("utf-8", "surrogatepass")
                    raw_ran += 1
                else:
                    raw = json.dumps(scenario["request"]).encode("utf-8")
                proc, _ = run_cli(raw)
                resp = one_object(self, proc)
                self.assertEqual(resp["status"], expect["status"])
                if expect["status"] == "ok":
                    request = scenario["request"]
                    self.assertEqual(resp["utility"], expect["utility"])
                    self.assertEqual(checker.check_response(request, resp), [])
                    recomputed = checker.response_for(request, resp["selected"])
                    self.assertEqual(resp["tokens"], recomputed["tokens"])
                    self.assertEqual(resp["covered"], recomputed["covered"])
                    self.assertEqual(resp["utility"], recomputed["utility"])
                    if "optimal_selections" in expect:
                        self.assertIn(resp["selected"], expect["optimal_selections"])
                else:
                    self.assertEqual(set(resp), {"status", "reason"})
                    self.assertTrue(isinstance(resp["reason"], str) and resp["reason"])
                    if "request" in scenario and expect["status"] == "infeasible":
                        self.assertEqual(checker.check_response(scenario["request"], resp), [])
                ran[expect["status"]] += 1
        self.assertEqual(ran, EXPECTED_COUNTS)
        self.assertEqual(raw_ran, 10)


if __name__ == "__main__":
    unittest.main()
