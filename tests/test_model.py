"""Tests for dcp_model: visibility, supersession, closures, conflicts, feasibility and legality."""

from __future__ import annotations

import json
import os
import unittest

import dcp_model
from dcp_model import Infeasible, build_problem

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def card(cid, version="v0", requires=(), supersedes=(), group=None, tokens=1, covers=()):
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


def request(cards, versions=None, head="v0", budget=100, mandatory=(), pairs=(), features=None):
    """Build a request dict in the validated shape; the default graph is the single version v0."""
    return {
        "versions": versions if versions is not None else [{"id": "v0", "parents": []}],
        "cards": list(cards),
        "features": dict(features or {}),
        "head": head,
        "budget": budget,
        "mandatory": list(mandatory),
        "contradictions": [list(pair) for pair in pairs],
    }


def mask_of(p, *ids):
    """Return the bitmask of the named active cards."""
    mask = 0
    for cid in ids:
        mask |= 1 << p.ids.index(cid)
    return mask


def closure_ids(p, cid):
    return dcp_model.mask_ids(p, p.closure[p.ids.index(cid)])


DIAMOND = [
    {"id": "root", "parents": []},
    {"id": "left", "parents": ["root"]},
    {"id": "right", "parents": ["root"]},
    {"id": "merge", "parents": ["left", "right"]},
]


class TestVisibility(unittest.TestCase):
    def test_build_problem_merge_head_sees_both_branches(self):
        cards = [card("a", "root"), card("b", "left"), card("c", "right"), card("d", "merge")]

        p = build_problem(request(cards, versions=DIAMOND, head="merge"))

        self.assertEqual(p.ids, ("a", "b", "c", "d"))
        self.assertEqual(p.n, 4)

    def test_build_problem_branch_head_hides_sibling_and_descendant(self):
        cards = [card("a", "root"), card("b", "left"), card("c", "right"), card("d", "merge")]

        p = build_problem(request(cards, versions=DIAMOND, head="left"))

        self.assertEqual(p.ids, ("a", "b"))

    def test_build_problem_deep_version_chain_does_not_recurse(self):
        versions = [{"id": "v0", "parents": []}]
        versions += [{"id": f"v{k}", "parents": [f"v{k - 1}"]} for k in range(1, 96)]
        cards = [card("old", "v0"), card("new", "v95")]

        p = build_problem(request(cards, versions=versions, head="v95"))

        self.assertEqual(p.ids, ("new", "old"))


class TestSupersession(unittest.TestCase):
    CHAIN = [
        {"id": "v0", "parents": []},
        {"id": "v1", "parents": ["v0"]},
        {"id": "v2", "parents": ["v1"]},
    ]

    def test_build_problem_chain_leaves_only_newest_active(self):
        cards = [card("a", "v0"), card("b", "v1", supersedes=["a"]), card("c", "v2", supersedes=["b"])]

        p = build_problem(request(cards, versions=self.CHAIN, head="v2"))

        self.assertEqual(p.ids, ("c",))
        self.assertEqual(p.n, 1)

    def test_build_problem_superseded_superseder_still_deactivates(self):
        # b is itself superseded by c, yet b's own supersession of x must still hold.
        cards = [
            card("a", "v0"),
            card("x", "v0"),
            card("b", "v1", supersedes=["a", "x"]),
            card("c", "v2", supersedes=["b"]),
        ]

        p = build_problem(request(cards, versions=self.CHAIN, head="v2"))

        self.assertEqual(p.ids, ("c",))

    def test_build_problem_invisible_superseder_does_not_deactivate(self):
        cards = [card("a", "root"), card("b", "right", supersedes=["a"])]

        p = build_problem(request(cards, versions=DIAMOND, head="left"))

        self.assertEqual(p.ids, ("a",))

    def test_build_problem_head_before_superseder_keeps_older_card(self):
        cards = [card("a", "v0"), card("b", "v1", supersedes=["a"]), card("c", "v2", supersedes=["b"])]

        p = build_problem(request(cards, versions=self.CHAIN, head="v1"))

        self.assertEqual(p.ids, ("b",))

    def test_build_problem_active_count_includes_unusable_cards(self):
        cards = [card("a", "v0"), card("b", "v1", supersedes=["a"]), card("d", "v1", requires=["a"])]

        p = build_problem(request(cards, versions=self.CHAIN, head="v2"))

        self.assertEqual(p.n, 2)
        self.assertEqual(p.ids, ("b", "d"))


class TestClosures(unittest.TestCase):
    def test_build_problem_requires_on_superseded_card_is_unusable(self):
        versions = [{"id": "v0", "parents": []}, {"id": "v1", "parents": ["v0"]}]
        cards = [card("a", "v0"), card("b", "v1", supersedes=["a"]), card("d", "v1", requires=["a"])]

        p = build_problem(request(cards, versions=versions, head="v1"))

        i = p.ids.index("d")
        self.assertEqual(p.closure[i], 0)
        self.assertEqual(p.usable, mask_of(p, "b"))

    def test_build_problem_requires_on_invisible_card_is_unusable(self):
        cards = [card("a", "left", requires=["z"]), card("z", "right")]

        p = build_problem(request(cards, versions=DIAMOND, head="left"))

        self.assertEqual(p.ids, ("a",))
        self.assertEqual(p.closure[0], 0)
        self.assertEqual(p.usable, 0)

    def test_build_problem_dead_requirement_propagates_to_dependents(self):
        cards = [card("a", "left", requires=["b"]), card("b", "left", requires=["z"]), card("z", "right")]

        p = build_problem(request(cards, versions=DIAMOND, head="left"))

        self.assertEqual(p.closure, (0, 0))

    def test_build_problem_requirement_cycle_is_taken_together(self):
        cards = [
            card("a", requires=["b"], tokens=3),
            card("b", requires=["c"], tokens=4),
            card("c", requires=["a"], tokens=5),
            card("d", requires=["a"], tokens=7),
        ]

        p = build_problem(request(cards))

        for cid in ("a", "b", "c"):
            self.assertEqual(closure_ids(p, cid), ["a", "b", "c"])
            self.assertEqual(p.closure_tokens[p.ids.index(cid)], 12)
        self.assertEqual(closure_ids(p, "d"), ["a", "b", "c", "d"])
        self.assertEqual(p.closure_tokens[p.ids.index("d")], 19)

    def test_build_problem_self_requirement_closure_is_the_card(self):
        p = build_problem(request([card("a", requires=["a"], tokens=9)]))

        self.assertEqual(p.closure, (1,))
        self.assertEqual(p.closure_tokens, (9,))
        self.assertEqual(p.usable, 1)

    def test_build_problem_shared_requirement_is_charged_once(self):
        cards = [
            card("base", tokens=10),
            card("l", requires=["base"], tokens=2),
            card("r", requires=["base"], tokens=3),
            card("top", requires=["l", "r"], tokens=4),
        ]

        p = build_problem(request(cards))

        self.assertEqual(p.closure_tokens[p.ids.index("top")], 19)

    def test_build_problem_long_requirement_chain_does_not_recurse(self):
        count = 500
        cards = [card(f"c{k:03d}", requires=[f"c{k + 1:03d}"] if k + 1 < count else []) for k in range(count)]

        p = build_problem(request(cards, budget=8192))

        self.assertEqual(p.closure[0], (1 << count) - 1)
        self.assertEqual(p.closure_tokens[0], count)
        self.assertEqual(p.closure[count - 1], 1 << (count - 1))
        self.assertEqual(p.dependents[count - 1], (1 << count) - 1)

    def test_build_problem_closure_aggregates_cover_and_conflict(self):
        cards = [
            card("a", requires=["b"], covers=["f1"]),
            card("b", covers=["f2"], group="g"),
            card("c", group="g"),
            card("d"),
        ]

        p = build_problem(request(cards, pairs=[("a", "d")], features={"f1": 5, "f2": 7, "f3": 9}))

        i = p.ids.index("a")
        self.assertEqual(dcp_model.fmask_ids(p, p.closure_cover[i]), ["f1", "f2"])
        self.assertEqual(dcp_model.mask_ids(p, p.closure_conflict[i]), ["c", "d"])

    def test_build_problem_dependents_lists_every_card_whose_closure_contains_it(self):
        cards = [card("a", requires=["b"]), card("b", requires=["c"]), card("c"), card("d")]

        p = build_problem(request(cards))

        self.assertEqual(dcp_model.mask_ids(p, p.dependents[p.ids.index("c")]), ["a", "b", "c"])
        self.assertEqual(dcp_model.mask_ids(p, p.dependents[p.ids.index("a")]), ["a"])
        self.assertEqual(dcp_model.mask_ids(p, p.dependents[p.ids.index("d")]), ["d"])


class TestConflicts(unittest.TestCase):
    def test_build_problem_pair_inside_closure_is_unusable(self):
        cards = [card("a", requires=["b"]), card("b")]

        p = build_problem(request(cards, pairs=[("b", "a")]))

        self.assertNotEqual(p.closure[p.ids.index("a")], 0)
        self.assertEqual(p.usable, mask_of(p, "b"))

    def test_build_problem_same_group_inside_closure_is_unusable(self):
        cards = [card("a", requires=["b"], group="g"), card("b", group="g")]

        p = build_problem(request(cards))

        self.assertEqual(p.usable, mask_of(p, "b"))

    def test_build_problem_pair_with_inactive_endpoint_is_inert(self):
        versions = [{"id": "v0", "parents": []}, {"id": "v1", "parents": ["v0"]}]
        cards = [card("a", "v0"), card("b", "v1", supersedes=["a"]), card("c", "v1")]

        p = build_problem(request(cards, versions=versions, head="v1", pairs=[("a", "c")]))

        self.assertEqual(p.ids, ("b", "c"))
        self.assertEqual(p.conflict, (0, 0))
        self.assertTrue(dcp_model.is_legal(p, mask_of(p, "b", "c")))

    def test_build_problem_pair_is_not_transferred_to_successor(self):
        versions = [{"id": "v0", "parents": []}, {"id": "v1", "parents": ["v0"]}]
        cards = [card("a", "v0"), card("b", "v1", supersedes=["a"]), card("c", "v0")]

        p = build_problem(request(cards, versions=versions, head="v1", pairs=[("c", "a")]))

        self.assertEqual(p.conflict[p.ids.index("b")], 0)

    def test_build_problem_pairs_are_symmetric_and_not_transitive(self):
        cards = [card("a"), card("b"), card("c")]

        p = build_problem(request(cards, pairs=[("a", "b"), ("c", "b")]))

        self.assertEqual(dcp_model.mask_ids(p, p.conflict[p.ids.index("b")]), ["a", "c"])
        self.assertEqual(dcp_model.mask_ids(p, p.conflict[p.ids.index("a")]), ["b"])
        self.assertTrue(dcp_model.is_legal(p, mask_of(p, "a", "c")))

    def test_build_problem_group_conflict_excludes_self_and_null_group(self):
        cards = [card("a", group="g"), card("b", group="g"), card("c"), card("d")]

        p = build_problem(request(cards))

        self.assertEqual(dcp_model.mask_ids(p, p.conflict[p.ids.index("a")]), ["b"])
        self.assertEqual(p.conflict[p.ids.index("c")], 0)
        self.assertTrue(dcp_model.is_legal(p, mask_of(p, "c", "d")))

    def test_build_problem_conflict_with_mandatory_is_unusable(self):
        cards = [card("m"), card("a", requires=["b"]), card("b"), card("c", group="g"), card("n", group="g")]

        p = build_problem(request(cards, mandatory=["m", "n"], pairs=[("b", "m")]))

        self.assertEqual(p.mandatory, mask_of(p, "m", "n"))
        self.assertEqual(p.usable, 0)

    def test_build_problem_closure_over_budget_with_mandatory_is_unusable(self):
        cards = [card("m", tokens=6), card("a", requires=["m"], tokens=4), card("b", tokens=5)]

        p = build_problem(request(cards, budget=10, mandatory=["m"]))

        self.assertEqual(p.usable, mask_of(p, "a"))


class TestMandatory(unittest.TestCase):
    def test_build_problem_mandatory_superseded_raises_infeasible(self):
        versions = [{"id": "v0", "parents": []}, {"id": "v1", "parents": ["v0"]}]
        cards = [card("a", "v0"), card("b", "v1", supersedes=["a"])]

        with self.assertRaises(Infeasible):
            build_problem(request(cards, versions=versions, head="v1", mandatory=["a"]))

    def test_build_problem_mandatory_invisible_raises_infeasible(self):
        cards = [card("a", "left"), card("z", "right")]

        with self.assertRaises(Infeasible):
            build_problem(request(cards, versions=DIAMOND, head="left", mandatory=["z"]))

    def test_build_problem_mandatory_requiring_inactive_raises_infeasible(self):
        cards = [card("a", "left", requires=["z"]), card("z", "right")]

        with self.assertRaises(Infeasible):
            build_problem(request(cards, versions=DIAMOND, head="left", mandatory=["a"]))

    def test_build_problem_mandatory_closure_with_pair_raises_infeasible(self):
        cards = [card("a", requires=["b"]), card("b")]

        with self.assertRaises(Infeasible):
            build_problem(request(cards, mandatory=["a"], pairs=[("a", "b")]))

    def test_build_problem_two_mandatory_cards_in_one_group_raises_infeasible(self):
        cards = [card("a", group="g"), card("b", group="g")]

        with self.assertRaises(Infeasible):
            build_problem(request(cards, mandatory=["a", "b"]))

    def test_build_problem_mandatory_over_budget_raises_infeasible(self):
        cards = [card("a", requires=["b"], tokens=6), card("b", tokens=5)]

        with self.assertRaises(Infeasible):
            build_problem(request(cards, budget=10, mandatory=["a"]))

    def test_build_problem_mandatory_at_exact_budget_is_feasible(self):
        cards = [card("a", requires=["b"], tokens=6), card("b", tokens=5)]

        p = build_problem(request(cards, budget=11, mandatory=["a"]))

        self.assertEqual(p.mandatory, 0b11)
        self.assertEqual(p.usable, 0)
        self.assertTrue(dcp_model.is_legal(p, p.mandatory))

    def test_build_problem_infeasible_reason_is_nonempty_ascii(self):
        with self.assertRaises(Infeasible) as caught:
            build_problem(request([card("a", tokens=5)], budget=4, mandatory=["a"]))

        reason = str(caught.exception)
        self.assertTrue(reason)
        self.assertTrue(reason.isascii())

    def test_build_problem_empty_mandatory_at_budget_zero_is_feasible(self):
        p = build_problem(request([card("a")], budget=0))

        self.assertEqual(p.mandatory, 0)
        self.assertEqual(p.usable, 0)
        self.assertTrue(dcp_model.is_legal(p, 0))

    def test_build_problem_no_cards_is_feasible(self):
        p = build_problem(request([], budget=0, features={"f": 3}))

        self.assertEqual(p.n, 0)
        self.assertEqual(p.ids, ())
        self.assertEqual(p.feat_ids, ("f",))
        self.assertTrue(dcp_model.is_legal(p, 0))


class TestIsLegal(unittest.TestCase):
    def setUp(self):
        versions = [{"id": "v0", "parents": []}, {"id": "v1", "parents": ["v0"]}]
        cards = [
            card("m", tokens=2),
            card("a", requires=["b"], tokens=3),
            card("b", tokens=3),
            card("g1", group="g", tokens=1),
            card("g2", group="g", tokens=1),
            card("x", tokens=1),
            card("y", tokens=1),
            card("big", tokens=9),
            card("old", "v0"),
            card("new", "v1", supersedes=["old"], tokens=1),
            card("needs_old", "v1", requires=["old"], tokens=1),
        ]
        self.p = build_problem(
            request(cards, versions=versions, head="v1", budget=10, mandatory=["m"], pairs=[("x", "y")])
        )

    def test_is_legal_accepts_a_legal_set(self):
        self.assertTrue(dcp_model.is_legal(self.p, mask_of(self.p, "m", "a", "b", "g1", "x")))

    def test_is_legal_rejects_card_outside_active_set(self):
        self.assertNotIn("old", self.p.ids)
        self.assertFalse(dcp_model.is_legal(self.p, self.p.mandatory | (1 << self.p.n)))
        self.assertFalse(dcp_model.is_legal(self.p, -1))

    def test_is_legal_rejects_card_requiring_inactive_card(self):
        self.assertFalse(dcp_model.is_legal(self.p, mask_of(self.p, "m", "needs_old")))

    def test_is_legal_rejects_missing_mandatory(self):
        self.assertFalse(dcp_model.is_legal(self.p, mask_of(self.p, "x")))
        self.assertFalse(dcp_model.is_legal(self.p, 0))

    def test_is_legal_rejects_open_requirement_closure(self):
        self.assertFalse(dcp_model.is_legal(self.p, mask_of(self.p, "m", "a")))

    def test_is_legal_rejects_two_cards_in_one_group(self):
        self.assertFalse(dcp_model.is_legal(self.p, mask_of(self.p, "m", "g1", "g2")))

    def test_is_legal_rejects_contradiction_pair(self):
        self.assertFalse(dcp_model.is_legal(self.p, mask_of(self.p, "m", "x", "y")))

    def test_is_legal_rejects_over_budget_and_allows_equality(self):
        self.assertFalse(dcp_model.is_legal(self.p, mask_of(self.p, "m", "big")))
        self.assertTrue(dcp_model.is_legal(self.p, mask_of(self.p, "m", "a", "b", "g1", "x")))
        self.assertEqual(dcp_model.mask_tokens(self.p, mask_of(self.p, "m", "a", "b", "g1", "x")), 10)


class TestMaskHelpers(unittest.TestCase):
    def setUp(self):
        cards = [card("b", tokens=4, covers=["f2", "f1"]), card("a", tokens=3, covers=["f2"]), card("c", tokens=5)]
        self.p = build_problem(request(cards, features={"f3": 100, "f1": 5, "f2": 7}))

    def test_problem_orders_ids_and_features_ascending(self):
        self.assertEqual(self.p.ids, ("a", "b", "c"))
        self.assertEqual(self.p.tokens, (3, 4, 5))
        self.assertEqual(self.p.feat_ids, ("f1", "f2", "f3"))
        self.assertEqual(self.p.feat_w, (5, 7, 100))

    def test_mask_tokens_sums_distinct_cards(self):
        self.assertEqual(dcp_model.mask_tokens(self.p, 0b111), 12)
        self.assertEqual(dcp_model.mask_tokens(self.p, 0), 0)

    def test_cover_weight_counts_repeated_feature_once(self):
        fmask = dcp_model.mask_cover(self.p, 0b011)

        self.assertEqual(dcp_model.fmask_ids(self.p, fmask), ["f1", "f2"])
        self.assertEqual(dcp_model.cover_weight(self.p, fmask), 12)

    def test_mask_ids_returns_ascending_ids(self):
        self.assertEqual(dcp_model.mask_ids(self.p, 0b101), ["a", "c"])
        self.assertEqual(dcp_model.mask_ids(self.p, 0), [])

    def test_problem_is_frozen(self):
        with self.assertRaises(AttributeError):
            self.p.budget = 1


class TestSampleSession(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(_ROOT, "resources", "director_session.json"), encoding="utf-8") as handle:
            cls.req = json.load(handle)
        cls.p = build_problem(cls.req)

    def test_sample_has_seven_active_cards_without_jacket(self):
        self.assertEqual(self.p.n, 7)
        self.assertEqual(
            self.p.ids, ("amber_arrival", "closeup", "coat", "moon", "neon", "portrait", "sleeve_detail")
        )

    def test_sample_closures_match_hand_walk(self):
        expected = {
            "portrait": (["portrait"], 32),
            "coat": (["coat", "portrait"], 55),
            "neon": (["neon"], 20),
            "moon": (["moon"], 18),
            "closeup": (["closeup", "portrait"], 47),
            "sleeve_detail": (["portrait", "sleeve_detail"], 44),
            "amber_arrival": (["amber_arrival", "coat", "neon", "portrait"], 102),
        }
        for cid, (members, tokens) in expected.items():
            with self.subTest(card=cid):
                self.assertEqual(closure_ids(self.p, cid), members)
                self.assertEqual(self.p.closure_tokens[self.p.ids.index(cid)], tokens)

    def test_sample_mandatory_closure_is_portrait(self):
        self.assertEqual(dcp_model.mask_ids(self.p, self.p.mandatory), ["portrait"])

    def test_sample_amber_arrival_is_active_but_not_usable(self):
        self.assertIn("amber_arrival", self.p.ids)
        self.assertEqual(
            dcp_model.mask_ids(self.p, self.p.usable), ["closeup", "coat", "moon", "neon", "sleeve_detail"]
        )

    def test_sample_conflicts_match_groups_and_pairs(self):
        expected = {
            "coat": ["sleeve_detail"],
            "sleeve_detail": ["coat"],
            "moon": ["amber_arrival", "neon"],
            "neon": ["moon"],
            "amber_arrival": ["moon"],
            "portrait": [],
            "closeup": [],
        }
        for cid, others in expected.items():
            with self.subTest(card=cid):
                self.assertEqual(dcp_model.mask_ids(self.p, self.p.conflict[self.p.ids.index(cid)]), others)

    def test_sample_best_legal_utility_is_61(self):
        p = self.p
        best = 0
        winners = []
        for mask in range(1 << p.n):
            if not dcp_model.is_legal(p, mask):
                continue
            utility = dcp_model.cover_weight(p, dcp_model.mask_cover(p, mask))
            if utility > best:
                best, winners = utility, [mask]
            elif utility == best:
                winners.append(mask)

        self.assertEqual(best, 61)
        self.assertIn(["closeup", "moon", "portrait", "sleeve_detail"], [dcp_model.mask_ids(p, m) for m in winners])
        self.assertIn(["closeup", "neon", "portrait", "sleeve_detail"], [dcp_model.mask_ids(p, m) for m in winners])

    def test_sample_text_does_not_change_the_problem(self):
        stripped = json.loads(json.dumps(self.req))
        for entry in stripped["cards"]:
            entry.pop("text", None)

        self.assertEqual(build_problem(stripped), self.p)


if __name__ == "__main__":
    unittest.main()
