"""Self-tests for the independent checker, oracle and generators, pinned to hand-derived values."""

from __future__ import annotations

import copy
import json
import os
import random
import re
import time
import unittest

import checker
import gen
import oracle

_ID_RE = re.compile(r"\A[A-Za-z0-9._:\-]{1,64}\Z")

_SAMPLE_INLINE = {
    "versions": [
        {"id": "draft", "parents": []},
        {"id": "club", "parents": ["draft"]},
        {"id": "rooftop", "parents": ["draft"]},
        {"id": "review", "parents": ["club", "rooftop"]},
    ],
    "cards": [
        {"id": "portrait", "version": "draft", "supersedes": [], "requires": [], "conflict_group": None,
         "tokens": 32, "covers": ["identity", "face"]},
        {"id": "jacket", "version": "draft", "supersedes": [], "requires": ["portrait"],
         "conflict_group": "outerwear", "tokens": 16, "covers": ["costume"]},
        {"id": "coat", "version": "club", "supersedes": ["jacket"], "requires": ["portrait"],
         "conflict_group": "outerwear", "tokens": 23, "covers": ["costume", "silhouette"]},
        {"id": "neon", "version": "club", "supersedes": [], "requires": [], "conflict_group": "palette",
         "tokens": 20, "covers": ["lighting", "palette"]},
        {"id": "moon", "version": "rooftop", "supersedes": [], "requires": [], "conflict_group": "palette",
         "tokens": 18, "covers": ["lighting", "palette"]},
        {"id": "amber_arrival", "version": "club", "supersedes": [], "requires": ["coat", "neon"],
         "conflict_group": None, "tokens": 27, "covers": ["location", "continuity"]},
        {"id": "closeup", "version": "review", "supersedes": [], "requires": ["portrait"],
         "conflict_group": None, "tokens": 15, "covers": ["face", "continuity"]},
        {"id": "sleeve_detail", "version": "review", "supersedes": [], "requires": ["portrait"],
         "conflict_group": None, "tokens": 12, "covers": ["gesture", "costume"]},
    ],
    "features": {"identity": 14, "face": 7, "costume": 9, "silhouette": 3, "lighting": 8, "palette": 5,
                 "location": 11, "continuity": 12, "gesture": 6},
    "head": "review",
    "budget": 100,
    "mandatory": ["portrait"],
    "contradictions": [["coat", "sleeve_detail"], ["moon", "amber_arrival"]],
}


def load_sample() -> dict:
    """The sample session from disk when present, otherwise the inline copy."""
    for path in ("director_session.json", os.path.join("resources", "director_session.json")):
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as handle:
                return json.load(handle)
    return copy.deepcopy(_SAMPLE_INLINE)


def tiny(*, pairs=(), mandatory=(), budget=100, requires=None, groups=None, versions=None, head="v0",
         card_versions=None) -> dict:
    """Cards a, b, c (10 tokens each) covering fa=20, fb=30, fc=40 respectively."""
    requires = requires or {}
    groups = groups or {}
    card_versions = card_versions or {}
    cards = []
    for cid in ("a", "b", "c"):
        cards.append({
            "id": cid,
            "version": card_versions.get(cid, "v0"),
            "supersedes": [],
            "requires": list(requires.get(cid, [])),
            "conflict_group": groups.get(cid),
            "tokens": 10,
            "covers": ["f" + cid],
        })
    return {
        "versions": versions or [{"id": "v0", "parents": []}],
        "cards": cards,
        "features": {"fa": 20, "fb": 30, "fc": 40},
        "head": head,
        "budget": budget,
        "mandatory": list(mandatory),
        "contradictions": [list(p) for p in pairs],
    }


def assert_valid_request(case: unittest.TestCase, request: dict) -> None:
    """Structural input-contract checks, written here so generators are not their own judge."""
    case.assertEqual(set(request), {"versions", "cards", "features", "head", "budget", "mandatory", "contradictions"})
    version_ids = [v["id"] for v in request["versions"]]
    card_ids = [c["id"] for c in request["cards"]]
    case.assertTrue(1 <= len(version_ids) <= 96)
    case.assertTrue(len(card_ids) <= 500)
    case.assertTrue(len(request["features"]) <= 1024)
    case.assertEqual(len(set(version_ids)), len(version_ids))
    case.assertEqual(len(set(card_ids)), len(card_ids))
    for ident in version_ids + card_ids + list(request["features"]):
        case.assertRegex(ident, _ID_RE)
    parents = {}
    for version in request["versions"]:
        case.assertEqual(set(version), {"id", "parents"})
        case.assertTrue(len(version["parents"]) <= 8)
        case.assertEqual(len(set(version["parents"])), len(version["parents"]))
        case.assertTrue(set(version["parents"]) <= set(version_ids))
        parents[version["id"]] = version["parents"]
    ancestors = {}
    for vid in version_ids:
        seen, stack = set(), list(parents[vid])
        while stack:
            cur = stack.pop()
            if cur not in seen:
                seen.add(cur)
                stack.extend(parents[cur])
        case.assertNotIn(vid, seen, "version graph has a cycle")
        ancestors[vid] = seen
    by_id = {c["id"]: c for c in request["cards"]}
    for card in request["cards"]:
        case.assertTrue({"id", "version", "supersedes", "requires", "conflict_group", "tokens", "covers"}
                        <= set(card) <= {"id", "version", "supersedes", "requires", "conflict_group", "tokens",
                                         "covers", "text"})
        case.assertIn(card["version"], parents)
        for key in ("supersedes", "requires"):
            case.assertTrue(len(card[key]) <= 8)
            case.assertEqual(len(set(card[key])), len(card[key]))
            case.assertTrue(set(card[key]) <= set(card_ids))
        for older in card["supersedes"]:
            case.assertIn(by_id[older]["version"], ancestors[card["version"]])
        if card["conflict_group"] is not None:
            case.assertRegex(card["conflict_group"], _ID_RE)
        case.assertIs(type(card["tokens"]), int)
        case.assertTrue(1 <= card["tokens"] <= 512)
        case.assertTrue(len(card["covers"]) <= 64)
        case.assertEqual(len(set(card["covers"])), len(card["covers"]))
        case.assertTrue(set(card["covers"]) <= set(request["features"]))
    for weight in request["features"].values():
        case.assertIs(type(weight), int)
        case.assertTrue(1 <= weight <= 1000)
    case.assertIn(request["head"], parents)
    case.assertIs(type(request["budget"]), int)
    case.assertTrue(0 <= request["budget"] <= 8192)
    case.assertEqual(len(set(request["mandatory"])), len(request["mandatory"]))
    case.assertTrue(set(request["mandatory"]) <= set(card_ids))
    case.assertTrue(len(request["contradictions"]) <= 10000)
    unordered = set()
    for pair in request["contradictions"]:
        case.assertEqual(len(pair), 2)
        case.assertNotEqual(pair[0], pair[1])
        case.assertTrue(set(pair) <= set(card_ids))
        unordered.add(frozenset(pair))
    case.assertEqual(len(unordered), len(request["contradictions"]))


class SampleSessionTests(unittest.TestCase):
    def test_sample_has_seven_active_cards(self):
        active = checker.active_cards(load_sample())
        self.assertEqual(active, {"portrait", "coat", "neon", "moon", "amber_arrival", "closeup", "sleeve_detail"})

    def test_sample_best_utility_is_61(self):
        self.assertEqual(oracle.best_utility(load_sample()), 61)

    def test_sample_best_set_passes_checker(self):
        request = load_sample()
        utility, selected = oracle.best_set(request)
        response = checker.response_for(request, selected)
        self.assertEqual(response["utility"], utility)
        self.assertEqual(checker.check_response(request, response), [])

    def test_inline_copy_matches_disk_semantics(self):
        self.assertEqual(oracle.best_utility(copy.deepcopy(_SAMPLE_INLINE)), 61)
        self.assertEqual(len(checker.active_cards(_SAMPLE_INLINE)), 7)


class TinyPublicRequestTests(unittest.TestCase):
    def test_i_353b_nontransitive_pairs_best_60(self):
        request = tiny(pairs=[("a", "b"), ("b", "c")])
        self.assertTrue(checker.expected_feasible(request))
        self.assertEqual(oracle.best_set(request), (60, ["a", "c"]))

    def test_i_5568_group_and_redundant_pair_best_70(self):
        request = tiny(groups={"a": "g", "b": "g"}, pairs=[("b", "a")])
        self.assertTrue(checker.expected_feasible(request))
        self.assertEqual(oracle.best_set(request), (70, ["b", "c"]))

    def test_i_f4bb_invisible_branch_selected_b_c_utility_70(self):
        request = tiny(
            versions=[{"id": "v0", "parents": []}, {"id": "left", "parents": ["v0"]},
                      {"id": "right", "parents": ["v0"]}],
            head="left", card_versions={"a": "right"}, pairs=[("a", "b")], mandatory=["b", "c"])
        self.assertEqual(checker.active_cards(request), {"b", "c"})
        self.assertTrue(checker.expected_feasible(request))
        self.assertEqual(oracle.best_set(request), (70, ["b", "c"]))
        ok = {"status": "ok", "selected": ["b", "c"], "tokens": 20, "covered": ["fb", "fc"], "utility": 70}
        self.assertEqual(checker.check_response(request, ok), [])

    def test_i_6bf2_requires_cycle_with_pair_is_infeasible(self):
        request = tiny(requires={"a": ["b"], "b": ["a"]}, pairs=[("a", "b")], mandatory=["a"])
        self._assert_infeasible(request)

    def test_i_354f_requires_chain_with_pair_is_infeasible(self):
        request = tiny(requires={"a": ["b"], "b": ["c"]}, pairs=[("a", "c")], mandatory=["a"])
        self._assert_infeasible(request)

    def _assert_infeasible(self, request):
        self.assertFalse(checker.expected_feasible(request))
        with self.assertRaises(LookupError):
            oracle.best_utility(request)
        infeasible = {"status": "infeasible", "reason": "mandatory closure is contradictory"}
        self.assertEqual(checker.check_response(request, infeasible), [])
        claimed = checker.response_for(request, ["a", "b", "c"])
        self.assertTrue(checker.check_response(request, claimed))

    def test_i_93a2_and_i_57be_invalid_requests_accept_only_invalid_shape(self):
        for pairs in ([["a", "a"]], [["a", "b", "c"]]):
            request = tiny()
            request["contradictions"] = pairs
            good = {"status": "invalid", "reason": "bad contradiction pair"}
            self.assertEqual(checker.check_response(request, good, request_valid=False), [])
            for bad in ({"status": "invalid", "reason": ""}, {"status": "invalid"},
                        {"status": "invalid", "reason": 3}, {"status": "invalid", "reason": "x", "extra": 1},
                        {"status": "infeasible", "reason": "x"},
                        {"status": "ok", "selected": [], "tokens": 0, "covered": [], "utility": 0}):
                self.assertTrue(checker.check_response(request, bad, request_valid=False), bad)


class LegalityConditionTests(unittest.TestCase):
    """One deliberately illegal response per legal-set condition, each with honest totals."""

    def _errors(self, request, selected):
        return checker.check_response(request, checker.response_for(request, selected))

    def _assert_condition(self, errors, number):
        self.assertTrue(any(e.startswith(f"condition {number}:") for e in errors), errors)

    def test_condition_1_inactive_card_rejected(self):
        self._assert_condition(self._errors(load_sample(), ["jacket", "portrait"]), 1)

    def test_condition_1_invisible_card_rejected(self):
        request = tiny(versions=[{"id": "v0", "parents": []}, {"id": "side", "parents": ["v0"]}],
                       card_versions={"a": "side"})
        self._assert_condition(self._errors(request, ["a"]), 1)

    def test_condition_1_unknown_id_rejected(self):
        response = {"status": "ok", "selected": ["zz"], "tokens": 0, "covered": [], "utility": 0}
        self._assert_condition(checker.check_response(tiny(), response), 1)

    def test_condition_2_missing_mandatory_rejected(self):
        self._assert_condition(self._errors(tiny(mandatory=["b"]), ["a"]), 2)

    def test_condition_3_incomplete_closure_rejected(self):
        self._assert_condition(self._errors(tiny(requires={"a": ["b"], "b": ["c"]}), ["a", "b"]), 3)

    def test_condition_3_requirement_on_inactive_card_can_never_be_met(self):
        request = load_sample()
        request["cards"][7]["requires"] = ["jacket"]
        self.assertEqual(request["cards"][7]["id"], "sleeve_detail")
        self._assert_condition(self._errors(request, ["portrait", "sleeve_detail"]), 3)
        self._assert_condition(self._errors(request, ["jacket", "portrait", "sleeve_detail"]), 1)

    def test_condition_4_two_cards_in_one_group_rejected(self):
        self._assert_condition(self._errors(tiny(groups={"a": "g", "b": "g"}), ["a", "b"]), 4)

    def test_condition_5_pair_rejected_in_either_orientation(self):
        self._assert_condition(self._errors(tiny(pairs=[("a", "b")]), ["a", "b"]), 5)
        self._assert_condition(self._errors(tiny(pairs=[("b", "a")]), ["a", "b"]), 5)

    def test_condition_6_over_budget_rejected_and_equality_allowed(self):
        self._assert_condition(self._errors(tiny(budget=19), ["a", "b"]), 6)
        self.assertEqual(self._errors(tiny(budget=20), ["a", "b"]), [])

    def test_empty_selection_legal_at_budget_zero(self):
        request = tiny(budget=0)
        self.assertEqual(self._errors(request, []), [])
        self.assertEqual(oracle.best_utility(request), 0)

    def test_self_requirement_is_selectable(self):
        request = tiny(requires={"a": ["a"]})
        self.assertEqual(self._errors(request, ["a"]), [])
        self.assertEqual(oracle.best_utility(request), 90)


class ResponseShapeTests(unittest.TestCase):
    def setUp(self):
        self.request = tiny()
        self.good = {"status": "ok", "selected": ["a", "c"], "tokens": 20, "covered": ["fa", "fc"], "utility": 60}

    def _bad(self, **changes):
        response = dict(self.good)
        response.update(changes)
        return checker.check_response(self.request, response)

    def test_good_response_passes(self):
        self.assertEqual(checker.check_response(self.request, self.good), [])

    def test_shape_and_total_violations_rejected(self):
        cases = {
            "bool tokens": {"tokens": True},
            "float tokens": {"tokens": 20.0},
            "float utility": {"utility": 60.0},
            "wrong tokens": {"tokens": 19},
            "wrong utility": {"utility": 61},
            "unsorted selected": {"selected": ["c", "a"]},
            "repeated selected": {"selected": ["a", "a", "c"]},
            "selected not list": {"selected": "ac"},
            "selected non-string": {"selected": ["a", 3]},
            "unsorted covered": {"covered": ["fc", "fa"]},
            "missing covered feature": {"covered": ["fa"]},
            "extra covered feature": {"covered": ["fa", "fb", "fc"]},
            "extra key": {"reason": "why"},
            "unknown status": {"status": "OK"},
        }
        for name, changes in cases.items():
            with self.subTest(name):
                self.assertTrue(self._bad(**changes))

    def test_missing_key_and_non_object_rejected(self):
        for key in ("selected", "tokens", "covered", "utility", "status"):
            response = dict(self.good)
            del response[key]
            self.assertTrue(checker.check_response(self.request, response), key)
        self.assertTrue(checker.check_response(self.request, [self.good]))

    def test_status_must_match_feasibility(self):
        wrongly = {"status": "infeasible", "reason": "gave up"}
        self.assertTrue(checker.check_response(self.request, wrongly))
        self.assertTrue(checker.check_response(self.request, {"status": "invalid", "reason": "no"}))
        self.assertTrue(checker.check_response(self.request, {"status": "infeasible", "reason": ""}))
        self.assertTrue(checker.check_response(
            self.request, {"status": "infeasible", "reason": "x", "certificate": {}}))


class CertificateTests(unittest.TestCase):
    def setUp(self):
        self.request = tiny()
        self.response = {"status": "ok", "selected": ["a", "b", "c"], "tokens": 30,
                         "covered": ["fa", "fb", "fc"], "utility": 90}

    def _check(self, certificate):
        response = dict(self.response)
        response["certificate"] = certificate
        return checker.check_response(self.request, response)

    def test_bound_formula_hand_derived(self):
        weights = {"fa": 20, "fb": 30, "fc": 40}
        zero = {"scale": 1, "budget_price": 0, "feature_prices": {"fa": 0, "fb": 0, "fc": 0}}
        self.assertEqual(checker.certificate_bound(self.request, zero), (90, 1))
        full = {"scale": 1, "budget_price": 0, "feature_prices": weights}
        self.assertEqual(checker.certificate_bound(self.request, full), (90, 1))
        # 100*1 + (20-10) + (30-10) + (40-10) + 0 = 160
        priced = {"scale": 1, "budget_price": 1, "feature_prices": weights}
        self.assertEqual(checker.certificate_bound(self.request, priced), (160, 1))
        # scale 2: 100*3 + max(0,40-30) + max(0,60-30) + max(0,80-30) + 0 = 390
        scaled = {"scale": 2, "budget_price": 3, "feature_prices": {"fa": 40, "fb": 60, "fc": 80}}
        self.assertEqual(checker.certificate_bound(self.request, scaled), (390, 2))

    def test_bound_sums_over_active_cards_only(self):
        request = tiny(versions=[{"id": "v0", "parents": []}, {"id": "side", "parents": ["v0"]}],
                       card_versions={"c": "side"})
        full = {"scale": 1, "budget_price": 0, "feature_prices": {"fa": 20, "fb": 30, "fc": 40}}
        # active a, b contribute 20 + 30; invisible c contributes nothing; slack is 0
        self.assertEqual(checker.certificate_bound(request, full), (50, 1))

    def test_valid_certificate_accepted(self):
        self.assertEqual(self._check({"scale": 1, "budget_price": 0,
                                      "feature_prices": {"fa": 20, "fb": 30, "fc": 40}}), [])
        self.assertEqual(self._check({"scale": 1000000, "budget_price": 90000000,
                                      "feature_prices": {"fa": 0, "fb": 0, "fc": 40000000}}), [])

    def test_malformed_certificates_rejected_with_prefix(self):
        prices = {"fa": 20, "fb": 30, "fc": 40}
        cases = [
            None,
            {"scale": 1, "budget_price": 0},
            {"scale": 1, "budget_price": 0, "feature_prices": prices, "note": "x"},
            {"scale": 0, "budget_price": 0, "feature_prices": prices},
            {"scale": 1000001, "budget_price": 0, "feature_prices": prices},
            {"scale": True, "budget_price": 0, "feature_prices": prices},
            {"scale": 1, "budget_price": -1, "feature_prices": prices},
            {"scale": 1, "budget_price": 91, "feature_prices": prices},
            {"scale": 1, "budget_price": False, "feature_prices": prices},
            {"scale": 1, "budget_price": 0, "feature_prices": {"fa": 20, "fb": 30}},
            {"scale": 1, "budget_price": 0, "feature_prices": {**prices, "fd": 0}},
            {"scale": 1, "budget_price": 0, "feature_prices": {**prices, "fa": 21}},
            {"scale": 1, "budget_price": 0, "feature_prices": {**prices, "fa": -1}},
            {"scale": 1, "budget_price": 0, "feature_prices": {**prices, "fa": 1.0}},
            {"scale": 1, "budget_price": 0, "feature_prices": [20, 30, 40]},
        ]
        for certificate in cases:
            with self.subTest(certificate=certificate):
                errors = self._check(certificate)
                self.assertTrue(errors)
                self.assertTrue(all(e.startswith("certificate:") for e in errors), errors)

    def test_profile_detection(self):
        self.assertTrue(checker.is_certificate_profile(tiny()))
        self.assertFalse(checker.is_certificate_profile(tiny(pairs=[("a", "b")])))
        self.assertFalse(checker.is_certificate_profile(tiny(groups={"a": "g"})))
        invisible_requires = tiny(versions=[{"id": "v0", "parents": []}, {"id": "side", "parents": ["v0"]}],
                                  card_versions={"a": "side"}, requires={"a": ["b"]})
        self.assertFalse(checker.is_certificate_profile(invisible_requires))
        shared = tiny()
        shared["cards"][1]["covers"] = ["fa"]
        self.assertFalse(checker.is_certificate_profile(shared))
        shared["versions"].append({"id": "side", "parents": ["v0"]})
        shared["cards"][1]["version"] = "side"
        self.assertTrue(checker.is_certificate_profile(shared))


class SupersessionTests(unittest.TestCase):
    def _chain(self, head):
        request = tiny(versions=[{"id": "v0", "parents": []}, {"id": "v1", "parents": ["v0"]},
                                 {"id": "v2", "parents": ["v1"]}, {"id": "br", "parents": ["v0"]}],
                       head=head, card_versions={"a": "v0", "b": "v1", "c": "v2"})
        request["cards"][1]["supersedes"] = ["a"]
        request["cards"][2]["supersedes"] = ["b"]
        return request

    def test_chain_leaves_only_newest_visible_card_active(self):
        self.assertEqual(checker.active_cards(self._chain("v2")), {"c"})
        self.assertEqual(checker.active_cards(self._chain("v1")), {"b"})
        self.assertEqual(checker.active_cards(self._chain("v0")), {"a"})

    def test_invisible_superseder_does_not_suppress(self):
        self.assertEqual(checker.active_cards(self._chain("br")), {"a"})

    def test_superseded_superseder_still_suppresses(self):
        request = self._chain("v2")
        request["cards"][2]["supersedes"] = ["b"]
        self.assertNotIn("a", checker.active_cards(request))

    def test_deep_version_and_requires_chains_do_not_recurse(self):
        request = gen.max_request(random.Random(5))
        self.assertEqual(len(checker.active_cards(request)), 500)
        self.assertEqual(len(checker.requires_closure(request, ["c0"])), 200)


class OracleTests(unittest.TestCase):
    def test_limit_exceeded_raises_value_error(self):
        request = gen.random_request(random.Random(1), 8, p_requires=0.0, p_group=0.0, n_pairs=0)
        with self.assertRaises(ValueError):
            oracle.best_utility(request, limit=7)

    def test_oracle_sets_pass_checker_on_random_requests(self):
        rng = random.Random(20261011)
        feasible = infeasible = 0
        for _ in range(120):
            request = gen.random_request(
                rng, rng.randint(0, 9), n_versions=rng.randint(1, 4), p_supersede=0.3,
                budget_ratio=rng.choice([0.2, 0.5, 1.0]), n_mandatory=rng.choice([0, 0, 1, 2]))
            try:
                utility, selected = oracle.best_set(request)
            except LookupError:
                infeasible += 1
                self.assertFalse(checker.expected_feasible(request))
                continue
            feasible += 1
            self.assertTrue(checker.expected_feasible(request))
            response = checker.response_for(request, selected)
            self.assertEqual(response["utility"], utility)
            self.assertEqual(checker.check_response(request, response), [])
        self.assertGreater(feasible, 10)
        self.assertGreater(infeasible, 5)

    def test_eighteen_active_cards_finish_in_a_few_seconds(self):
        request = gen.random_request(random.Random(3), 18, p_requires=0.0, p_group=0.0, n_pairs=0,
                                     budget_ratio=1.0)
        self.assertEqual(len(checker.active_cards(request)), 18)
        started = time.perf_counter()
        utility = oracle.best_utility(request)
        self.assertLess(time.perf_counter() - started, 10.0)
        covered = set()
        for card in request["cards"]:
            covered.update(card["covers"])
        self.assertEqual(utility, sum(request["features"][f] for f in covered))


class GeneratorTests(unittest.TestCase):
    def test_random_requests_satisfy_input_contract(self):
        rng = random.Random(7)
        for _ in range(60):
            request = gen.random_request(
                rng, rng.randint(0, 25), n_versions=rng.randint(1, 8), p_supersede=0.4,
                n_pairs=rng.choice([None, 0, 40]), n_mandatory=rng.randint(0, 3))
            assert_valid_request(self, request)

    def test_random_request_rejects_arguments_beyond_contract_limits(self):
        quiet = dict(p_requires=0.0, p_group=0.0, n_pairs=0)
        cases = [
            ("n_cards", (501,), dict(quiet, n_features=1, max_covers=0)),
            ("n_cards", (-1,), quiet),
            ("n_features", (1,), dict(quiet, n_features=1025)),
            ("n_features", (1,), dict(quiet, n_features=-1)),
            ("n_versions", (1,), dict(quiet, n_versions=97)),
            ("n_versions", (1,), dict(quiet, n_versions=0)),
            ("max_covers", (1,), dict(quiet, max_covers=65)),
            ("max_covers", (1,), dict(quiet, max_covers=-1)),
            ("max_tokens", (1,), dict(quiet, max_tokens=513)),
            ("max_tokens", (1,), dict(quiet, max_tokens=0)),
            ("n_pairs", (4,), dict(p_requires=0.0, p_group=0.0, n_pairs=10_001)),
            ("n_pairs", (4,), dict(p_requires=0.0, p_group=0.0, n_pairs=-1)),
            ("n_mandatory", (4,), dict(quiet, n_mandatory=-1)),
            ("budget_ratio", (4,), dict(quiet, budget_ratio=-0.5)),
            ("budget_ratio", (4,), dict(quiet, budget_ratio=float("inf"))),
            ("budget_ratio", (4,), dict(quiet, budget_ratio=float("nan"))),
        ]
        for name, args, kwargs in cases:
            with self.subTest(argument=name, args=args, kwargs=kwargs):
                with self.assertRaisesRegex(ValueError, name):
                    gen.random_request(random.Random(0), *args, **kwargs)

    def test_random_request_accepts_contract_boundary_values(self):
        request = gen.random_request(random.Random(0), 500, n_versions=96, n_features=1024, max_covers=64,
                                     max_tokens=512, n_pairs=10_000, budget_ratio=1000.0)
        assert_valid_request(self, request)
        self.assertEqual(len(request["cards"]), 500)
        self.assertEqual(len(request["features"]), 1024)
        self.assertEqual(len(request["versions"]), 96)
        self.assertEqual(len(request["contradictions"]), 10_000)
        self.assertEqual(request["budget"], 8192)
        self.assertLessEqual(max(len(c["covers"]) for c in request["cards"]), 64)
        self.assertLessEqual(max(c["tokens"] for c in request["cards"]), 512)

    def test_random_request_caps_pairs_at_the_distinct_pairs_available(self):
        request = gen.random_request(random.Random(0), 4, p_requires=0.0, p_group=0.0, n_pairs=10_000)
        assert_valid_request(self, request)
        self.assertEqual(len(request["contradictions"]), 6)

    def test_random_request_accepts_zero_cards_and_zero_features(self):
        request = gen.random_request(random.Random(0), 0, n_features=0)
        assert_valid_request(self, request)
        self.assertEqual((request["cards"], request["features"]), ([], {}))

    def test_random_requests_with_mandatory_include_infeasible_ones(self):
        rng = random.Random(11)
        outcomes = {checker.expected_feasible(gen.random_request(rng, 8, n_versions=3, n_mandatory=2))
                    for _ in range(60)}
        self.assertEqual(outcomes, {True, False})

    def test_random_request_is_deterministic_for_a_seed(self):
        self.assertEqual(gen.random_request(random.Random(9), 12, n_versions=3, p_supersede=0.3),
                         gen.random_request(random.Random(9), 12, n_versions=3, p_supersede=0.3))

    def test_permute_preserves_best_utility_on_30_requests(self):
        rng = random.Random(42)
        for _ in range(30):
            request = gen.random_request(
                rng, rng.randint(1, 10), n_versions=rng.randint(1, 4), p_supersede=0.3,
                n_mandatory=rng.choice([0, 0, 1]))
            before = copy.deepcopy(request)
            permuted = gen.permute_request(rng, request)
            self.assertEqual(request, before, "permute_request must not mutate its input")
            assert_valid_request(self, permuted)
            self.assertEqual(len(checker.active_cards(permuted)), len(checker.active_cards(request)))
            self.assertEqual(self._solve(permuted), self._solve(request))

    @staticmethod
    def _solve(request):
        try:
            return oracle.best_utility(request)
        except LookupError:
            return "infeasible"

    def test_permute_renames_and_keeps_sample_optimum(self):
        request = load_sample()
        permuted = gen.permute_request(random.Random(4), request)
        self.assertFalse({c["id"] for c in permuted["cards"]} & {c["id"] for c in request["cards"]})
        self.assertEqual(oracle.best_utility(permuted), 61)
        self.assertEqual(len(checker.active_cards(permuted)), 7)

    def test_max_request_is_valid_and_at_contract_maxima(self):
        request = gen.max_request(random.Random(1))
        assert_valid_request(self, request)
        self.assertEqual(len(request["versions"]), 96)
        self.assertEqual(len(request["cards"]), 500)
        self.assertEqual(len(checker.active_cards(request)), 500)
        self.assertEqual(len(request["features"]), 1024)
        self.assertEqual(len(request["contradictions"]), 10000)
        self.assertEqual(request["budget"], 8192)
        self.assertEqual(max(len(c["covers"]) for c in request["cards"]), 64)
        self.assertEqual(max(c["tokens"] for c in request["cards"]), 512)
        self.assertEqual(len({c["conflict_group"] for c in request["cards"]} - {None}), 20)
        self.assertEqual(checker.requires_closure(request, ["c200"]), {"c200", "c201", "c202"})
        self.assertTrue(checker.expected_feasible(request))
        self.assertFalse(checker.is_certificate_profile(request))

    def test_max_request_profile_matches_certificate_profile(self):
        request = gen.max_request(random.Random(2), profile=True)
        assert_valid_request(self, request)
        self.assertEqual(len(checker.active_cards(request)), 500)
        self.assertTrue(checker.is_certificate_profile(request))
        self.assertEqual(request["contradictions"], [])
        self.assertTrue(all(len(c["covers"]) == 1 for c in request["cards"]))


class IndependenceTests(unittest.TestCase):
    def test_helpers_import_nothing_from_the_solver(self):
        here = os.path.dirname(os.path.abspath(__file__))
        for name in ("checker.py", "oracle.py", "gen.py"):
            with open(os.path.join(here, name), encoding="utf-8") as handle:
                source = handle.read()
            self.assertIsNone(re.search(r"^\s*(import|from)\s+(dcp_|context_solver)", source, re.M), name)


if __name__ == "__main__":
    unittest.main()
