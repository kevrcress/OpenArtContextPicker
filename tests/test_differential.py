"""``dcp_pipeline.run`` against the independent checker and oracle on generated requests."""

import copy
import json
import random
import sys
import time
import unittest

import checker
import gen
import oracle

import dcp_pipeline

N_REQUESTS = 320
N_MUTATIONS = 50


def run(raw: bytes) -> dict:
    return dcp_pipeline.run(raw, time.perf_counter())


def generated_requests() -> list:
    """Valid requests with 1 to 14 active cards: half with mandatory cards, a third with supersession."""
    rng = random.Random(20261011)
    out = []
    index = 0
    while len(out) < N_REQUESTS:
        index += 1
        supersede = index % 3 == 0
        request = gen.random_request(
            rng,
            rng.randint(1, 14),
            n_versions=rng.randint(2, 5) if supersede else 1,
            p_supersede=0.4 if supersede else 0.0,
            p_requires=rng.choice((0.0, 0.3, 0.6)),
            p_group=rng.choice((0.0, 0.3)),
            max_covers=rng.randint(1, 4),
            budget_ratio=rng.choice((0.0, 0.2, 0.5, 0.8, 1.5)),
            n_mandatory=rng.randint(1, 3) if index % 2 == 0 else 0,
        )
        if 1 <= len(checker.active_cards(request)) <= 14:
            out.append(request)
    return out


def exact_range_requests() -> list:
    """Twelve feasible requests with 19 to 22 active cards, small enough for the exhaustive oracle."""
    rng = random.Random(1924)
    out = []
    for n in [19] * 6 + [20] * 4 + [21, 22]:
        while True:
            request = gen.random_request(
                rng, n, p_requires=rng.choice((0.2, 0.4)), p_group=rng.choice((0.0, 0.3)),
                n_pairs=rng.choice((n // 2, n)), n_features=2 * n, max_covers=rng.choice((3, 6)),
                budget_ratio=rng.choice((0.3, 0.5, 0.7)), n_mandatory=rng.choice((0, 1)),
            )
            if len(checker.active_cards(request)) == n and checker.expected_feasible(request):
                out.append(request)
                break
    return out


def reduced_core_request(rng, n_core: int, n_total: int) -> tuple:
    """Return ``(core, full)``: ``full`` has ``n_total`` active cards and the same optimum as ``core``.

    ``full`` is ``core`` plus filler cards; every core card, feature weight, pair and the budget
    is unchanged. No card requires a filler and no filler is mandatory, so dropping the fillers
    from a legal set of ``full`` leaves a legal set of ``core``. Its utility is the same, because
    a filler either covers nothing or costs more tokens than the budget and is in no legal set.
    Every legal set of ``core`` is legal in ``full``, so the two maxima are equal.
    """
    core = gen.random_request(rng, n_core, p_requires=rng.choice((0.2, 0.4)), p_group=rng.choice((0.0, 0.3)),
                              n_pairs=rng.choice((n_core // 2, n_core)), n_features=2 * n_core,
                              max_covers=rng.choice((3, 6)), max_tokens=40, budget_ratio=rng.choice((0.3, 0.5, 0.7)))
    full = copy.deepcopy(core)
    core_ids = [c["id"] for c in core["cards"]]
    feature_ids = sorted(core["features"])
    for j in range(n_total - n_core):
        filler = {"id": f"filler{j:02d}", "version": core["head"], "supersedes": [], "conflict_group": None}
        assert filler["id"] not in core_ids
        if j % 2 and core["budget"] < 512:
            filler.update(tokens=rng.randint(core["budget"] + 1, 512), requires=[],
                          covers=rng.sample(feature_ids, rng.randint(1, 6)))
        else:
            filler.update(tokens=rng.randint(1, 40), requires=rng.sample(core_ids, rng.randint(0, 1)), covers=[])
            if rng.random() < 0.5:
                full["contradictions"].append([filler["id"], rng.choice(core_ids)])
        full["cards"].append(filler)
    rng.shuffle(full["cards"])
    return core, full


def _card(request, index=0):
    return request["cards"][index % len(request["cards"])]


def _set(path_setter):
    def mutate(request, rng):
        path_setter(request, rng)
        return json.dumps(request).encode("utf-8")
    return mutate


def _raw(edit):
    def mutate(request, rng):
        return edit(json.dumps(request)).encode("utf-8")
    return mutate


def _ids(request):
    return [c["id"] for c in request["cards"]]


# Each entry breaks exactly one rule of the input contract on an otherwise valid request.
MUTATIONS = {
    "budget below zero": _set(lambda r, g: r.__setitem__("budget", -1)),
    "budget above 8192": _set(lambda r, g: r.__setitem__("budget", 8193)),
    "budget is a boolean": _set(lambda r, g: r.__setitem__("budget", True)),
    "budget is a float": _set(lambda r, g: r.__setitem__("budget", 5.0)),
    "budget is a string": _set(lambda r, g: r.__setitem__("budget", "5")),
    "head missing": _set(lambda r, g: r.pop("head")),
    "unknown top-level key": _set(lambda r, g: r.__setitem__("notes", [])),
    "head is an unknown version": _set(lambda r, g: r.__setitem__("head", "no-such-version")),
    "tokens zero": _set(lambda r, g: _card(r, g.randrange(99)).__setitem__("tokens", 0)),
    "tokens above 512": _set(lambda r, g: _card(r, g.randrange(99)).__setitem__("tokens", 513)),
    "unknown card key": _set(lambda r, g: _card(r, g.randrange(99)).__setitem__("weight", 1)),
    "card without covers": _set(lambda r, g: _card(r, g.randrange(99)).pop("covers")),
    "covers an unknown feature": _set(lambda r, g: _card(r, g.randrange(99))["covers"].append("no-such-feature")),
    "duplicate card id": _set(lambda r, g: r["cards"].append(copy.deepcopy(_card(r)))),
    "card on an unknown version": _set(lambda r, g: _card(r, g.randrange(99)).__setitem__("version", "no-such-version")),
    "card id with a space": _set(lambda r, g: _card(r).__setitem__("id", "bad id")),
    "requires an unknown card": _set(lambda r, g: _card(r, g.randrange(99)).__setitem__("requires", ["no-such-card"])),
    "supersedes itself": _set(lambda r, g: _card(r).__setitem__("supersedes", [_card(r)["id"]])),
    "conflict group is a number": _set(lambda r, g: _card(r, g.randrange(99)).__setitem__("conflict_group", 5)),
    "text is too long": _set(lambda r, g: _card(r, g.randrange(99)).__setitem__("text", "x" * 2049)),
    "mandatory names an unknown card": _set(lambda r, g: r["mandatory"].append("no-such-card")),
    "contradiction with itself": _set(lambda r, g: r["contradictions"].append([_ids(r)[0], _ids(r)[0]])),
    "contradiction with an unknown card": _set(lambda r, g: r["contradictions"].append([_ids(r)[0], "no-such-card"])),
    "contradiction in both orientations": _set(lambda r, g: r.__setitem__(
        "contradictions", [[_ids(r)[0], _ids(r)[1]], [_ids(r)[1], _ids(r)[0]]])),
    "feature weight zero": _set(lambda r, g: r["features"].__setitem__("zero-weight", 0)),
    "feature weight above 1000": _set(lambda r, g: r["features"].__setitem__("heavy", 1001)),
    "version with an unknown parent": _set(lambda r, g: r["versions"][0]["parents"].append("no-such-version")),
    "cards is an object": _set(lambda r, g: r.__setitem__("cards", {})),
    "top level is an array": _raw(lambda text: "[" + text + "]"),
    "duplicate top-level key": _raw(lambda text: text[:-1] + ', "budget": 1}'),
    "trailing data": _raw(lambda text: text + " {}"),
    "truncated": _raw(lambda text: text[:-1]),
    "invalid UTF-8": lambda request, rng: json.dumps(request).encode("utf-8")[:-1] + b"\xff}",
    "byte order mark": lambda request, rng: b"\xef\xbb\xbf" + json.dumps(request).encode("utf-8"),
}


class DifferentialTest(unittest.TestCase):
    def test_generated_requests_agree_with_checker_and_oracle(self):
        requests = generated_requests()
        self.assertGreaterEqual(len(requests), 300)
        infeasible = 0
        disagreements = []
        sizes = set()
        for index, request in enumerate(requests):
            sizes.add(len(checker.active_cards(request)))
            resp = run(json.dumps(request).encode("utf-8"))
            problems = checker.check_response(request, resp)
            if not checker.expected_feasible(request):
                infeasible += 1
                if resp.get("status") != "infeasible":
                    problems.append(f"status {resp.get('status')!r}, expected infeasible")
            elif resp.get("status") != "ok":
                problems.append(f"status {resp.get('status')!r}, expected ok")
            elif resp["utility"] != oracle.best_utility(request):
                problems.append(f"utility {resp['utility']}, oracle {oracle.best_utility(request)}")
            if problems:
                disagreements.append((index, problems))
        sys.stderr.write(f"[differential] {len(requests)} requests, {infeasible} infeasible, "
                         f"active counts {min(sizes)}..{max(sizes)}, {len(disagreements)} disagreements\n")
        self.assertEqual(disagreements, [])
        self.assertGreater(infeasible, 0)
        self.assertLess(infeasible, len(requests) // 2)
        self.assertEqual(sizes, set(range(1, 15)))

    def _assert_exact(self, request: dict, expected: int, n_active: int, label: str) -> None:
        self.assertEqual(len(checker.active_cards(request)), n_active, label)
        resp = run(json.dumps(request).encode("utf-8"))
        diag = dict(dcp_pipeline.LAST_DIAG)
        self.assertEqual(checker.check_response(request, resp), [], label)
        self.assertEqual(resp["status"], "ok", label)
        self.assertEqual(resp["utility"], expected, label)
        self.assertLessEqual(diag["active"], dcp_pipeline.EXACT_MAX_ACTIVE, label)
        self.assertEqual((diag["method"], diag["active"], diag["proven"]), ("exact", n_active, True), label)

    def test_19_to_22_active_cards_are_exact_through_the_pipeline(self):
        requests = exact_range_requests()
        self.assertGreaterEqual(len(requests), 12)
        sizes = []
        for index, request in enumerate(requests):
            n = len(checker.active_cards(request))
            sizes.append(n)
            with self.subTest(index=index, active=n):
                self._assert_exact(request, oracle.best_utility(request, limit=22), n, f"request {index} active={n}")
        self.assertEqual(set(sizes), {19, 20, 21, 22})
        sys.stderr.write(f"[differential] {len(requests)} requests with 19..22 active cards match the oracle\n")

    def test_23_and_24_active_cards_with_a_reduced_core_are_exact_through_the_pipeline(self):
        rng = random.Random(2324)
        sizes = []
        for index in range(12):
            n_total = 23 + index % 2
            core, full = reduced_core_request(rng, rng.randint(12, 14), n_total)
            sizes.append(n_total)
            with self.subTest(index=index, active=n_total, core=len(core["cards"])):
                self._assert_exact(full, oracle.best_utility(core), n_total, f"reduced-core request {index}")
        self.assertEqual((sizes.count(23), sizes.count(24)), (6, 6))
        sys.stderr.write("[differential] 12 reduced-core requests with 23 or 24 active cards match the oracle\n")

    def test_single_rule_mutations_are_invalid(self):
        rng = random.Random(77)
        names = sorted(MUTATIONS)
        wrong = []
        for index in range(N_MUTATIONS):
            name = names[index % len(names)]
            request = gen.random_request(rng, rng.randint(3, 8), n_versions=2, n_mandatory=1, budget_ratio=2.0)
            self.assertNotEqual(run(json.dumps(request).encode("utf-8"))["status"], "invalid", name)
            resp = run(MUTATIONS[name](copy.deepcopy(request), rng))
            if checker.check_response(request, resp, request_valid=False):
                wrong.append((name, resp))
        sys.stderr.write(f"[differential] {N_MUTATIONS} mutations over {len(names)} rules, {len(wrong)} not answered invalid\n")
        self.assertEqual(wrong, [])
        self.assertGreaterEqual(N_MUTATIONS, len(names))


if __name__ == "__main__":
    unittest.main()
