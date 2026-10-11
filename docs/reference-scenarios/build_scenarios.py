"""Build the reference scenarios and their expected answers.

Every `ok` and `infeasible` expectation is computed by the brute-force oracle
below, which enumerates all subsets of the active cards. Every `invalid`
expectation is one deliberate mutation of a valid request, labelled by hand
against the contract.

Run: python3.11 -I docs/reference-scenarios/build_scenarios.py
Writes scenarios.json and README.md next to this file.
"""
from __future__ import annotations

import copy
import json
import pathlib
import random

HERE = pathlib.Path(__file__).resolve().parent
SAMPLE = json.loads((HERE.parent.parent / "resources" / "director_session.json").read_text(encoding="utf-8"))
MAX_LISTED = 12


def oracle(request):
    """Exhaustive answer for a request that is already known to be valid."""
    parents = {v["id"]: v["parents"] for v in request["versions"]}
    visible, stack = set(), [request["head"]]
    while stack:
        version = stack.pop()
        if version not in visible:
            visible.add(version)
            stack.extend(parents[version])
    cards = {c["id"]: c for c in request["cards"]}
    seen = [c for c in request["cards"] if c["version"] in visible]
    superseded = set()
    for c in seen:
        superseded.update(c["supersedes"])
    active = sorted(c["id"] for c in seen if c["id"] not in superseded)
    assert len(active) <= 18, "too many active cards for brute force"
    index = {cid: i for i, cid in enumerate(active)}
    pairs = [(index[a], index[b]) for a, b in request["contradictions"] if a in index and b in index]
    weights = request["features"]
    mandatory = request["mandatory"]
    result = {"active_cards": active, "visible_versions": sorted(visible)}
    if any(m not in index for m in mandatory):
        result.update(status="infeasible")
        return result
    best, winners = -1, []
    for mask in range(1 << len(active)):
        chosen = [active[i] for i in range(len(active)) if mask >> i & 1]
        chosen_set = set(chosen)
        if not set(mandatory) <= chosen_set:
            continue
        if any(not set(cards[c]["requires"]) <= chosen_set for c in chosen):
            continue
        groups = [cards[c]["conflict_group"] for c in chosen if cards[c]["conflict_group"] is not None]
        if len(groups) != len(set(groups)):
            continue
        if any(mask >> a & 1 and mask >> b & 1 for a, b in pairs):
            continue
        if sum(cards[c]["tokens"] for c in chosen) > request["budget"]:
            continue
        covered = set()
        for c in chosen:
            covered.update(cards[c]["covers"])
        utility = sum(weights[f] for f in covered)
        if utility > best:
            best, winners = utility, [chosen]
        elif utility == best:
            winners.append(chosen)
    if best < 0:
        result.update(status="infeasible")
        return result
    result.update(status="ok", utility=best, optimal_selection_count=len(winners))
    if len(winners) <= MAX_LISTED:
        result["optimal_selections"] = winners
    else:
        result["example_optimal_selections"] = winners[:3]
    return result


def card(cid, version, tokens, covers, supersedes=(), requires=(), group=None, text=None):
    out = {"id": cid, "version": version, "supersedes": list(supersedes), "requires": list(requires),
           "conflict_group": group, "tokens": tokens, "covers": list(covers)}
    if text is not None:
        out["text"] = text
    return out


def req(versions, cards, features, head, budget, mandatory=(), contradictions=()):
    return {"versions": [{"id": v, "parents": list(p)} for v, p in versions], "cards": cards,
            "features": features, "head": head, "budget": budget, "mandatory": list(mandatory),
            "contradictions": [list(p) for p in contradictions]}


def sample(**changes):
    out = copy.deepcopy(SAMPLE)
    out.update(changes)
    return out


def edit(fn, base=None):
    out = copy.deepcopy(SAMPLE if base is None else base)
    fn(out)
    return out


def by_id(request, cid):
    return next(c for c in request["cards"] if c["id"] == cid)


SCENARIOS = []


def solve(sid, group, title, trap, request, want_status, want_utility=None):
    answer = oracle(request)
    assert answer["status"] == want_status, (sid, answer)
    if want_utility is not None:
        assert answer["utility"] == want_utility, (sid, answer)
    expect = {k: v for k, v in answer.items() if k != "visible_versions"}
    SCENARIOS.append({"id": sid, "group": group, "title": title, "trap": trap, "request": request, "expect": expect})


def invalid(sid, title, rule, request=None, raw=None):
    entry = {"id": sid, "group": "invalid", "title": title, "trap": rule, "expect": {"status": "invalid"}}
    if raw is None:
        assert request != SAMPLE, sid
        entry["request"] = request
    else:
        entry["raw_stdin"] = raw
    SCENARIOS.append(entry)


# --- Group 1: the supplied sample session, varied one thing at a time ------------------------

G1 = "sample-variations"
solve("sample_baseline", G1, "The supplied session, unchanged",
      "Picking the club set (portrait, coat, neon, amber_arrival): it scores 69 but costs 102 tokens.",
      sample(), "ok", 61)
solve("sample_budget_102", G1, "Budget raised by two tokens to 102",
      "Staying on the 61-point answer. At 102 the club set fits exactly; equality with the budget is allowed.",
      sample(budget=102), "ok", 69)
solve("sample_budget_101", G1, "Budget 101, one token short of the club set",
      "Rounding or off-by-one on the budget check.",
      sample(budget=101), "ok", 61)
solve("sample_head_club", G1, "Head moved back to the club branch",
      "Selecting rooftop or review cards (moon, closeup, sleeve_detail). They are not visible from this head.",
      sample(head="club"), "ok")
solve("sample_head_rooftop", G1, "Head moved to the rooftop branch",
      "Treating the jacket as superseded. The coat lives on the club branch, which is invisible here, "
      "so the jacket is active again.",
      sample(head="rooftop"), "ok")
solve("sample_head_draft", G1, "Head moved back to the first draft",
      "Selecting anything decided after the draft.",
      sample(head="draft"), "ok")
solve("sample_budget_32", G1, "Budget 32, exactly the mandatory portrait",
      "Reporting infeasible because nothing useful fits beside the mandatory card.",
      sample(budget=32), "ok", 21)
solve("sample_budget_31", G1, "Budget 31, one token short of the mandatory portrait",
      "Returning ok with an empty or over-budget selection. The mandatory card cannot fit.",
      sample(budget=31), "infeasible")
solve("sample_budget_0_no_mandatory", G1, "Budget 0 and nothing mandatory",
      "Reporting infeasible. An empty selection is legal.",
      sample(budget=0, mandatory=[]), "ok", 0)
solve("sample_mandatory_jacket", G1, "The superseded jacket is made mandatory",
      "Selecting the jacket anyway, or swapping in the coat. A mandatory card that is not active has no legal set.",
      sample(mandatory=["portrait", "jacket"]), "infeasible")
solve("sample_mandatory_jacket_head_rooftop", G1, "Jacket mandatory, head on the rooftop branch",
      "Reporting infeasible. From this head the jacket is active.",
      sample(mandatory=["portrait", "jacket"], head="rooftop"), "ok")
solve("sample_mandatory_amber_arrival", G1, "The amber arrival is made mandatory",
      "Returning the arrival without everything it requires. Its closure costs 102 tokens against a budget of 100.",
      sample(mandatory=["portrait", "amber_arrival"]), "infeasible")
solve("sample_mandatory_amber_arrival_budget_102", G1, "Amber arrival mandatory, budget 102",
      "Reporting infeasible. The closure fits exactly.",
      sample(mandatory=["portrait", "amber_arrival"], budget=102), "ok", 69)
solve("sample_mandatory_coat_and_sleeve", G1, "Two contradictory cards are both mandatory",
      "Returning either one. The pair coat / sleeve_detail can never be selected together.",
      sample(mandatory=["coat", "sleeve_detail"]), "infeasible")
solve("sample_mandatory_neon_and_moon", G1, "Two cards from one conflict group are both mandatory",
      "Returning both palettes.",
      sample(mandatory=["neon", "moon"]), "infeasible")
solve("sample_mandatory_invisible", G1, "Head on the club branch, rooftop card mandatory",
      "Selecting moon. It is not visible from the club head.",
      sample(head="club", mandatory=["moon"]), "infeasible")
solve("sample_no_contradictions", G1, "The two contradiction pairs removed",
      "Still avoiding coat with sleeve_detail from memory of the text. Only supplied pairs count.",
      sample(contradictions=[]), "ok")
solve("sample_shuffled", G1, "Same session with arrays reversed and pairs flipped",
      "Any dependence on array order or pair orientation. The utility must equal the baseline.",
      edit(lambda r: (r["cards"].reverse(), r["versions"].reverse(), r["mandatory"].reverse(),
                      r.update(contradictions=[list(reversed(p)) for p in reversed(r["contradictions"])]))),
      "ok", 61)

# --- Group 2: one rule per scenario ---------------------------------------------------------

G2 = "single-rule"
chain_versions = [("v1", []), ("v2", ["v1"]), ("v3", ["v2"])]
chain_cards = [
    card("hair_silver", "v1", 10, ["hair"], text="Mara has a short silver bob."),
    card("hair_copper", "v2", 10, ["hair"], supersedes=["hair_silver"], text="Change her hair to copper."),
    card("hair_shaved", "v3", 30, ["hair"], supersedes=["hair_copper"], text="Actually, shave her head."),
    card("scarf", "v1", 10, ["costume"], text="She wears a green scarf."),
]
chain_features = {"hair": 10, "costume": 4}
solve("revision_chain_latest_too_big", G2, "Three revisions of one fact; only the newest is usable and it does not fit",
      "Falling back to an older, cheaper revision. hair_silver and hair_copper are both superseded.",
      req(chain_versions, chain_cards, chain_features, "v3", 20), "ok", 4)
solve("revision_chain_head_v2", G2, "The same chain viewed from the middle version",
      "Using hair_shaved (not visible yet) or hair_silver (already superseded).",
      req(chain_versions, chain_cards, chain_features, "v2", 20), "ok", 14)

redirect_cards = [
    card("jacket", "v1", 10, ["costume"]),
    card("coat", "v2", 10, ["costume"], supersedes=["jacket"]),
    card("sleeve", "v1", 5, ["gesture"], requires=["jacket"], text="Keep the jacket sleeve visible."),
    card("hat", "v1", 5, ["headwear"]),
]
redirect_features = {"costume": 9, "gesture": 20, "headwear": 2}
two_versions = [("v1", []), ("v2", ["v1"])]
solve("requirement_on_superseded_card", G2, "A card requires a card that has since been replaced",
      "Redirecting the requirement to the coat, or selecting the jacket. sleeve is active but can never be selected.",
      req(two_versions, redirect_cards, redirect_features, "v2", 30), "ok", 11)
solve("mandatory_requires_superseded_card", G2, "The same, with the dependent card mandatory",
      "Returning ok. The mandatory closure contains an inactive card.",
      req(two_versions, redirect_cards, redirect_features, "v2", 30, mandatory=["sleeve"]), "infeasible")

solve("contradiction_not_inherited", G2, "A contradiction names a card that was later replaced",
      "Carrying the jacket / rain contradiction over to the coat. The pair applies to those exact cards only.",
      req(two_versions,
          [card("jacket", "v1", 10, ["costume"]), card("coat", "v2", 10, ["costume"], supersedes=["jacket"]),
           card("rain", "v1", 10, ["weather"])],
          {"costume": 9, "weather": 6}, "v2", 20, contradictions=[("jacket", "rain")]), "ok", 15)

one_version = [("v1", [])]
solve("contradictions_not_transitive", G2, "fog clashes with sun, sun clashes with mist",
      "Assuming fog also clashes with mist and settling for sun alone (10).",
      req(one_version,
          [card("fog", "v1", 5, ["mood"]), card("sun", "v1", 5, ["light"]), card("mist", "v1", 5, ["texture"])],
          {"mood": 6, "light": 10, "texture": 6}, "v1", 100,
          contradictions=[("fog", "sun"), ("sun", "mist")]), "ok", 12)

solve("requirement_cycle_and_shared_requirement", G2,
      "A two-card requirement cycle, a self-requirement, and one prerequisite shared by two cards",
      "Charging the shared stage card twice (33 tokens, over budget), or looping forever on the cycle.",
      req(one_version,
          [card("duet_a", "v1", 10, ["melody"], requires=["duet_b"]),
           card("duet_b", "v1", 10, ["harmony"], requires=["duet_a"]),
           card("solo", "v1", 5, ["solo_line"], requires=["solo"]),
           card("stage", "v1", 8, []),
           card("spot_left", "v1", 6, ["left"], requires=["stage"]),
           card("spot_right", "v1", 6, ["right"], requires=["stage"])],
          {"melody": 5, "harmony": 5, "solo_line": 3, "left": 6, "right": 6}, "v1", 30), "ok", 15)

finale_cards = [
    card("finale", "v1", 5, ["climax"], requires=["confetti", "blackout"]),
    card("confetti", "v1", 5, ["sparkle"]),
    card("blackout", "v1", 5, ["drama"]),
]
finale_features = {"climax": 50, "sparkle": 4, "drama": 3}
solve("closure_contains_contradiction", G2, "A card requires two cards that contradict each other",
      "Rejecting the request as invalid, or selecting finale. The request is valid; finale is just unusable.",
      req(one_version, finale_cards, finale_features, "v1", 100, contradictions=[("confetti", "blackout")]), "ok", 4)
solve("mandatory_closure_contains_contradiction", G2, "The same, with that card mandatory",
      "Returning invalid. The contract asks for infeasible.",
      req(one_version, finale_cards, finale_features, "v1", 100, mandatory=["finale"],
          contradictions=[("confetti", "blackout")]), "infeasible")
solve("closure_contains_group_clash", G2, "A card requires two cards from the same conflict group",
      "Selecting wide_shot with both lenses.",
      req(one_version,
          [card("wide_shot", "v1", 5, ["scale"], requires=["lens_wide", "lens_tele"]),
           card("lens_wide", "v1", 5, ["depth"], group="lens"),
           card("lens_tele", "v1", 5, ["compression"], group="lens")],
          {"scale": 50, "depth": 4, "compression": 3}, "v1", 100), "ok", 4)

solve("shared_feature_counts_once", G2, "Two strong cards cover the same features",
      "Taking the two highest-scoring cards (19, because the second adds nothing). The best pair scores 26.",
      req(one_version,
          [card("hero_front", "v1", 10, ["identity", "face"]),
           card("hero_profile", "v1", 10, ["identity", "face", "hair"]),
           card("harbor", "v1", 10, ["location"]),
           card("violin", "v1", 10, ["prop"])],
          {"identity": 10, "face": 8, "hair": 1, "location": 7, "prop": 6}, "v1", 20), "ok", 26)
solve("density_greedy_trap", G2, "One dense card blocks two cards that together score more",
      "Greedy by value per token takes wide (7) and then nothing else fits. left + right scores 10.",
      req(one_version,
          [card("wide", "v1", 6, ["w"]), card("left", "v1", 5, ["l"]), card("right", "v1", 5, ["r"])],
          {"w": 7, "l": 5, "r": 5}, "v1", 10), "ok", 10)
solve("zero_cover_prerequisite", G2, "A valuable card needs a prerequisite that covers nothing",
      "Dropping the rig from `selected` or from the token total because it adds no utility.",
      req(one_version,
          [card("rig", "v1", 15, []), card("crane_shot", "v1", 10, ["spectacle"], requires=["rig"]),
           card("handheld", "v1", 20, ["intimacy"])],
          {"spectacle": 12, "intimacy": 11}, "v1", 25), "ok", 12)
solve("null_group_no_exclusivity", G2, "Several cards with no conflict group, plus two in one group",
      "Treating null as a group and selecting only one of the ungrouped cards.",
      req(one_version,
          [card("a", "v1", 5, ["fa"]), card("b", "v1", 5, ["fb"]), card("c", "v1", 5, ["fc"]),
           card("warm", "v1", 5, ["tone"], group="grade"), card("cool", "v1", 5, ["tone", "chill"], group="grade")],
          {"fa": 3, "fb": 3, "fc": 3, "tone": 4, "chill": 1}, "v1", 100), "ok", 14)
solve("tie_any_optimum", G2, "Two cards cover the same single feature at different costs",
      "Nothing to get wrong on utility: the cheap card, the dear card, or both are all acceptable answers.",
      req(one_version, [card("cheap", "v1", 5, ["f"]), card("dear", "v1", 9, ["f"])], {"f": 7}, "v1", 20), "ok", 7)
solve("empty_session", G2, "The empty session from the contract",
      "Rejecting an empty card list or a zero budget.",
      req([("v0", [])], [], {}, "v0", 0), "ok", 0)
solve("unrelated_branch_superseder", G2, "A replacement exists only on a branch the head never merged",
      "Letting the side-branch replacement deactivate the original. An invisible card never suppresses a visible one.",
      req([("main1", []), ("main2", ["main1"]), ("side", ["main1"])],
          [card("logo_old", "main1", 5, ["brand"]), card("logo_new", "side", 5, ["brand", "polish"],
                                                         supersedes=["logo_old"]),
           card("tagline", "main2", 5, ["copy"])],
          {"brand": 8, "polish": 5, "copy": 2}, "main2", 100), "ok", 10)

# --- Group 3: input that must be accepted ---------------------------------------------------

G3 = "must-accept"
solve("accept_text_omitted", G3, "Every card has its optional text removed",
      "Requiring `text`.", edit(lambda r: [c.pop("text") for c in r["cards"]]), "ok", 61)
solve("accept_text_empty_and_unicode", G3, "Empty text on one card, non-ASCII text on another",
      "Rejecting empty or non-ASCII text. Only identifiers are restricted to ASCII.",
      edit(lambda r: (by_id(r, "portrait").update(text=""),
                      by_id(r, "neon").update(text="Café néon — 夜の光"))), "ok", 61)
solve("accept_redundant_pair_in_group", G3, "A contradiction pair between two cards already in one group",
      "Rejecting the pair as redundant. The contract says it is valid.",
      edit(lambda r: r["contradictions"].append(["neon", "moon"])), "ok", 61)
solve("accept_pair_with_inactive_card", G3, "A contradiction pair that names the superseded jacket",
      "Rejecting it, or applying it to the coat.",
      edit(lambda r: r["contradictions"].append(["jacket", "closeup"])), "ok", 61)
solve("accept_identifier_characters", G3, "Identifiers using every allowed punctuation mark and the 64-character maximum",
      "An identifier pattern that is too narrow.",
      req([("v.1_a:b-c", [])],
          [card("c" * 64, "v.1_a:b-c", 5, ["f.1_a:b-c"], group="g.1_a:b-c"), card("Z9", "v.1_a:b-c", 5, ["F"])],
          {"f.1_a:b-c": 3, "F": 4}, "v.1_a:b-c", 10), "ok", 7)
solve("accept_unsorted_arrays", G3, "Children listed before parents, replacements before originals",
      "Assuming versions or cards arrive in topological order.",
      req([("v3", ["v2"]), ("v2", ["v1"]), ("v1", [])],
          [card("new", "v3", 5, ["f"], supersedes=["old"], requires=["base"]), card("old", "v1", 5, ["f", "g"]),
           card("base", "v1", 5, [])],
          {"f": 5, "g": 5}, "v3", 10), "ok", 5)
solve("accept_uncovered_feature_and_coverless_card", G3, "A feature no card covers and a card that covers nothing",
      "Rejecting either. Both are within the stated limits.",
      req(one_version, [card("blank", "v1", 5, []), card("real", "v1", 5, ["f"])], {"f": 2, "orphan": 9}, "v1", 10),
      "ok", 2)
solve("accept_limit_values", G3, "Tokens 512, weight 1000, budget 8192: the stated maxima",
      "Off-by-one on the upper limits.",
      req(one_version, [card("big", "v1", 512, ["f"]), card("small", "v1", 1, ["g"])], {"f": 1000, "g": 1}, "v1", 8192),
      "ok", 1001)

# --- Group 4: seeded mixed scenarios, 12 to 16 active cards --------------------------------

G4 = "seeded-mixed"


def seeded(seed, count, pair_count, with_mandatory):
    rng = random.Random(seed)
    ancestors = {"v0": [], "v1": ["v0"], "v2": ["v0", "v1"], "side": ["v0"]}
    features = {f"f{i}": rng.randint(1, 20) for i in range(count)}
    cards = []
    for i in range(count):
        version = rng.choice(["v0", "v0", "v1", "v1", "v2", "v2", "side"])
        older = [c["id"] for c in cards if c["version"] in ancestors[version]]
        supersedes = [rng.choice(older)] if older and rng.random() < 0.2 else []
        others = [c["id"] for c in cards]
        requires = rng.sample(others, k=min(len(others), rng.choice([1, 1, 2]))) if others and rng.random() < 0.35 else []
        group = rng.choice(["g0", "g1", "g2"]) if rng.random() < 0.3 else None
        covers = rng.sample(sorted(features), k=rng.randint(1, 3))
        cards.append(card(f"k{i:02d}", version, rng.randint(3, 30), covers, supersedes, requires, group))
    ids = [c["id"] for c in cards]
    pairs = set()
    while len(pairs) < pair_count:
        pairs.add(tuple(sorted(rng.sample(ids, 2))))
    request = req([("v0", []), ("v1", ["v0"]), ("v2", ["v1"]), ("side", ["v0"])], cards, features, "v2",
                  0, contradictions=sorted(pairs))
    active = oracle(dict(request, budget=0))["active_cards"]
    request["budget"] = sum(c["tokens"] for c in cards if c["id"] in active) * 2 // 5
    if with_mandatory:
        for candidate in active:
            request["mandatory"] = [candidate]
            if oracle(request)["status"] == "ok" and by_id(request, candidate)["requires"]:
                break
    return request


for seed, count, pair_count, with_mandatory in [(11, 18, 8, False), (23, 20, 12, True), (37, 22, 16, True)]:
    solve(f"seeded_{seed}", G4, f"Generated session, seed {seed}: branches, revisions, requirements, groups and pairs together",
          "No single trap. This checks exactness when every rule interacts.",
          seeded(seed, count, pair_count, with_mandatory), "ok")

# --- Group 5: input that must be rejected as invalid ---------------------------------------

invalid("invalid_missing_key", "`mandatory` is missing", "All seven top-level keys are required.",
        edit(lambda r: r.pop("mandatory")))
invalid("invalid_unknown_top_level_key", "Extra top-level key `note`", "Unknown object keys are invalid.",
        edit(lambda r: r.update(note="hello")))
invalid("invalid_unknown_card_key", "Extra card key `priority`", "Unknown keys inside card objects are invalid.",
        edit(lambda r: by_id(r, "portrait").update(priority=1)))
invalid("invalid_unknown_version_key", "Extra version key `label`", "Version objects have exactly `id` and `parents`.",
        edit(lambda r: r["versions"][0].update(label="first")))
invalid("invalid_card_missing_key", "A card without `covers`", "Each card has the seven required keys.",
        edit(lambda r: by_id(r, "closeup").pop("covers")))
invalid("invalid_duplicate_card_id", "Two cards share an ID", "Card IDs are unique.",
        edit(lambda r: r["cards"].append(copy.deepcopy(r["cards"][0]))))
invalid("invalid_duplicate_version_id", "Two versions share an ID", "Version IDs are unique.",
        edit(lambda r: r["versions"].append({"id": "draft", "parents": []})))
invalid("invalid_unknown_head", "`head` names no version", "`head` is an existing version ID.",
        sample(head="final"))
invalid("invalid_unknown_card_version", "A card's version does not exist", "`version` is an existing version ID.",
        edit(lambda r: by_id(r, "closeup").update(version="final")))
invalid("invalid_unknown_requirement", "`requires` names no card", "`requires` holds existing card IDs.",
        edit(lambda r: by_id(r, "closeup").update(requires=["ghost"])))
invalid("invalid_unknown_feature", "`covers` names no feature", "`covers` holds existing feature IDs.",
        edit(lambda r: by_id(r, "closeup").update(covers=["face", "ghost"])))
invalid("invalid_unknown_mandatory", "`mandatory` names no card", "`mandatory` holds existing card IDs.",
        sample(mandatory=["ghost"]))
invalid("invalid_duplicate_mandatory", "`mandatory` lists one card twice", "`mandatory` entries are distinct.",
        sample(mandatory=["portrait", "portrait"]))
invalid("invalid_duplicate_requires", "`requires` lists one card twice", "`requires` entries are distinct.",
        edit(lambda r: by_id(r, "closeup").update(requires=["portrait", "portrait"])))
invalid("invalid_duplicate_covers", "`covers` lists one feature twice", "`covers` entries are distinct.",
        edit(lambda r: by_id(r, "closeup").update(covers=["face", "face"])))
invalid("invalid_tokens_zero", "`tokens` is 0", "`tokens` is an integer from 1 to 512.",
        edit(lambda r: by_id(r, "closeup").update(tokens=0)))
invalid("invalid_tokens_513", "`tokens` is 513", "`tokens` is an integer from 1 to 512.",
        edit(lambda r: by_id(r, "closeup").update(tokens=513)))
invalid("invalid_tokens_boolean", "`tokens` is true", "Booleans are not integers.",
        edit(lambda r: by_id(r, "closeup").update(tokens=True)))
invalid("invalid_tokens_string", "`tokens` is the string \"15\"", "`tokens` is an integer.",
        edit(lambda r: by_id(r, "closeup").update(tokens="15")))
invalid("invalid_budget_negative", "`budget` is -1", "`budget` is an integer from 0 to 8,192.", sample(budget=-1))
invalid("invalid_budget_8193", "`budget` is 8193", "`budget` is an integer from 0 to 8,192.", sample(budget=8193))
invalid("invalid_budget_null", "`budget` is null", "Null is permitted only as `conflict_group`.", sample(budget=None))
invalid("invalid_weight_zero", "A feature weight of 0", "Weights are integers from 1 to 1,000.",
        edit(lambda r: r["features"].update(gesture=0)))
invalid("invalid_weight_1001", "A feature weight of 1001", "Weights are integers from 1 to 1,000.",
        edit(lambda r: r["features"].update(gesture=1001)))
invalid("invalid_supersedes_self", "A card supersedes itself", "A card cannot supersede itself.",
        edit(lambda r: by_id(r, "coat").update(supersedes=["coat"])))
invalid("invalid_supersedes_same_version", "A card supersedes a card from its own version",
        "The older card's version must be a strict ancestor.",
        edit(lambda r: by_id(r, "jacket").update(supersedes=["portrait"])))
invalid("invalid_supersedes_unrelated_branch", "A rooftop card supersedes a club card",
        "Superseding across unrelated branches is invalid.",
        edit(lambda r: by_id(r, "moon").update(supersedes=["neon"])))
invalid("invalid_supersedes_descendant", "A draft card supersedes a later club card",
        "The older card's version must be a strict ancestor, not a descendant.",
        edit(lambda r: by_id(r, "jacket").update(supersedes=["neon"])))
invalid("invalid_pair_both_orientations", "A contradiction supplied as [a,b] and [b,a]",
        "Supplying both orientations is a duplicate.",
        edit(lambda r: r["contradictions"].append(["sleeve_detail", "coat"])))
invalid("invalid_pair_repeated", "The same contradiction pair twice", "Pairs are distinct.",
        edit(lambda r: r["contradictions"].append(["coat", "sleeve_detail"])))
invalid("invalid_pair_self", "A card contradicting itself", "A self-pair is invalid.",
        edit(lambda r: r["contradictions"].append(["coat", "coat"])))
invalid("invalid_pair_three_elements", "A contradiction with three elements", "A pair has exactly two elements.",
        edit(lambda r: r["contradictions"].append(["coat", "moon", "neon"])))
invalid("invalid_pair_unknown_card", "A contradiction naming no card", "Each endpoint is an existing card ID.",
        edit(lambda r: r["contradictions"].append(["coat", "ghost"])))
invalid("invalid_pair_not_array", "A contradiction written as a string", "Each pair is a two-element array.",
        edit(lambda r: r["contradictions"].append("coat,moon")))
invalid("invalid_version_cycle", "The first draft lists the final review as its parent",
        "The version graph is acyclic.",
        edit(lambda r: r["versions"][0].update(parents=["review"])))
invalid("invalid_unknown_parent", "A version's parent does not exist", "`parents` holds existing version IDs.",
        edit(lambda r: r["versions"][1].update(parents=["ghost"])))
invalid("invalid_duplicate_parents", "A version lists one parent twice", "`parents` entries are distinct.",
        edit(lambda r: r["versions"][1].update(parents=["draft", "draft"])))
invalid("invalid_versions_empty", "`versions` is empty", "`versions` has 1 to 96 objects.",
        req([], [], {}, "v0", 0))
invalid("invalid_group_identifier_space", "A conflict group named \"outer wear\"",
        "Identifiers allow only letters, digits, `.`, `_`, `:` and `-`.",
        edit(lambda r: by_id(r, "jacket").update(conflict_group="outer wear")))
invalid("invalid_group_empty_string", "A conflict group that is an empty string",
        "An identifier has 1 to 64 characters.",
        edit(lambda r: by_id(r, "jacket").update(conflict_group="")))
invalid("invalid_card_id_65_chars", "A 65-character card ID", "An identifier has 1 to 64 characters.",
        req(one_version, [card("c" * 65, "v1", 5, [])], {}, "v1", 10))
invalid("invalid_feature_id_non_ascii", "A feature ID containing é", "Identifiers are ASCII.",
        req(one_version, [], {"café": 5}, "v1", 10))
invalid("invalid_text_null", "`text` is null", "Null is permitted only as `conflict_group`.",
        edit(lambda r: by_id(r, "closeup").update(text=None)))
invalid("invalid_text_2049_chars", "`text` is 2,049 characters", "`text` is at most 2,048 characters.",
        edit(lambda r: by_id(r, "closeup").update(text="x" * 2049)))
invalid("invalid_cards_not_array", "`cards` is an object", "All arrays and objects must have the stated types.",
        sample(cards={}))
invalid("invalid_precedence_over_infeasible", "Unknown key on a request that is also infeasible (budget 31)",
        "Invalid-input validation takes precedence over infeasibility.",
        edit(lambda r: r.update(budget=31, note="hello")))

BASE_TEXT = json.dumps(SAMPLE, ensure_ascii=False)


def swap(old, new):
    assert BASE_TEXT.count(old) == 1, old
    return BASE_TEXT.replace(old, new)


invalid("invalid_raw_duplicate_top_level_key", "`budget` appears twice with the same value",
        "Duplicate JSON object keys are invalid. The standard parser silently keeps the last one.",
        raw=swap('"budget": 100', '"budget": 100, "budget": 100'))
invalid("invalid_raw_duplicate_card_key", "One card has `tokens` twice",
        "Duplicate JSON object keys are invalid at every level.",
        raw=swap('"tokens": 32', '"tokens": 32, "tokens": 32'))
invalid("invalid_raw_tokens_fractional", "`tokens` written as 32.0",
        "Integer fields require integer notation without a fractional part.",
        raw=swap('"tokens": 32', '"tokens": 32.0'))
invalid("invalid_raw_budget_exponent", "`budget` written as 1e2",
        "Integer fields require integer notation without an exponent part.",
        raw=swap('"budget": 100', '"budget": 1e2'))
invalid("invalid_raw_nan_weight", "A feature weight of NaN", "Non-finite numbers are invalid.",
        raw=swap('"gesture": 6', '"gesture": NaN'))
invalid("invalid_raw_two_objects", "Two JSON objects on stdin", "The input is one JSON object.",
        raw=BASE_TEXT + "\n" + BASE_TEXT)
invalid("invalid_raw_top_level_array", "The request wrapped in an array", "The input is one JSON object.",
        raw="[" + BASE_TEXT + "]")
invalid("invalid_raw_truncated", "The request cut off mid-way", "The input is one JSON object.",
        raw=BASE_TEXT[: len(BASE_TEXT) // 2])
invalid("invalid_raw_empty", "Empty stdin", "The input is one JSON object.", raw="")
invalid("invalid_raw_deep_nesting", "100,000 nested arrays",
        "The input is one JSON object. The standard parser raises RecursionError here; it must not escape.",
        raw="[" * 100000 + "]" * 100000)

# --- Output --------------------------------------------------------------------------------

ids = [s["id"] for s in SCENARIOS]
assert len(ids) == len(set(ids))
document = {
    "schema": "reference-scenarios/1",
    "how_to_use": "Feed `raw_stdin` verbatim, or `request` serialized as JSON, to the solver on stdin. Expect exit "
                  "code 0 and `expect.status`. For `ok`, the response utility must equal `expect.utility`, the "
                  "selection must be legal, and `tokens` and `covered` must match a recomputation from `selected`. "
                  "When `optimal_selections` is present it lists every legal maximum-utility selection.",
    "scenarios": SCENARIOS,
}
(HERE / "scenarios.json").write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

TITLES = {"sample-variations": "The supplied session, varied one thing at a time",
          "single-rule": "One rule per scenario",
          "must-accept": "Input that must be accepted",
          "seeded-mixed": "Generated sessions where every rule interacts",
          "invalid": "Input that must be rejected as invalid"}
lines = ["# Reference scenarios", "",
         f"{len(SCENARIOS)} scenarios with expected answers, generated by `build_scenarios.py`. "
         "The machine-readable form is `scenarios.json`; this file is the same content for reading.", "",
         "Expected answers for `ok` and `infeasible` come from a brute-force search over every subset of the "
         "active cards. Expected `invalid` answers are single mutations of a valid request, labelled by hand "
         "against the contract. If the solver disagrees with a scenario, check the contract before changing "
         "either side.", ""]
for group, heading in TITLES.items():
    rows = [s for s in SCENARIOS if s["group"] == group]
    lines += [f"## {heading}", ""]
    if group == "invalid":
        lines += ["| ID | What is wrong | Contract rule |", "|---|---|---|"]
        lines += [f"| `{s['id']}` | {s['title']} | {s['trap']} |" for s in rows]
    else:
        lines += ["| ID | Situation | Expected | The mistake it catches |", "|---|---|---|---|"]
        for s in rows:
            e = s["expect"]
            if e["status"] == "ok":
                picks = e.get("optimal_selections") or e["example_optimal_selections"]
                first = ", ".join(picks[0]) or "nothing"
                more = e["optimal_selection_count"] - 1
                expected = f"ok, utility {e['utility']}: {first}" + (f" (+{more} tied)" if more else "")
            else:
                expected = e["status"]
            lines.append(f"| `{s['id']}` | {s['title']} | {expected} | {s['trap']} |")
    lines.append("")
(HERE / "README.md").write_text("\n".join(lines), encoding="utf-8")
counts = {}
for s in SCENARIOS:
    counts[s["expect"]["status"]] = counts.get(s["expect"]["status"], 0) + 1
print(len(SCENARIOS), "scenarios", counts)
