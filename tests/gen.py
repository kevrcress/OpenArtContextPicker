"""Request generators for tests: random valid requests, contract-maximum requests, equivalent permutations.

Independent of every solver module. Every generator takes a seeded
``random.Random`` so tests stay deterministic.
"""

from __future__ import annotations

import copy

_ID_ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._:-"
_MAX_TOKENS = 512
_MAX_BUDGET = 8192
_MAX_LINKS = 8
_MAX_COVERS = 64
_MAX_PAIRS = 10_000
_MAX_CARDS = 500
_MAX_FEATURES = 1024
_MAX_VERSIONS = 96


def _require_range(name: str, value, low: int, high: int) -> None:
    """Raise ``ValueError`` unless ``value`` is an integer within ``low..high``."""
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"{name} must be an integer in {low}..{high} (contract limit), got {value!r}")


def _strict_ancestors(versions: list) -> dict:
    """Map each version id to the set of its strict ancestors (iterative)."""
    parents = {v["id"]: v["parents"] for v in versions}
    result = {}
    for vid in parents:
        seen = set()
        stack = list(parents[vid])
        while stack:
            cur = stack.pop()
            if cur not in seen:
                seen.add(cur)
                stack.extend(parents[cur])
        result[vid] = seen
    return result


def _random_pairs(rng, ids: list, count: int) -> list:
    """``count`` distinct unordered pairs of distinct ids, each in one random orientation."""
    n = len(ids)
    count = min(count, n * (n - 1) // 2, _MAX_PAIRS)
    chosen = set()
    while len(chosen) < count:
        i, j = rng.sample(range(n), 2)
        chosen.add((min(i, j), max(i, j)))
    pairs = []
    for i, j in sorted(chosen):
        pair = [ids[i], ids[j]]
        if rng.random() < 0.5:
            pair.reverse()
        pairs.append(pair)
    rng.shuffle(pairs)
    return pairs


def random_request(rng, n_cards, *, n_versions=1, p_requires=0.3, p_group=0.3, n_pairs=None, p_supersede=0.0,
                   n_features=None, max_covers=3, max_tokens=40, budget_ratio=0.5, n_mandatory=0) -> dict:
    """Always returns a request that satisfies the input contract (valid), feasible or not.

    Raises ``ValueError`` when an argument asks for more than the contract
    allows. The budget is capped at 8,192 and the pair count at the number of
    distinct card pairs.
    """
    _require_range("n_cards", n_cards, 0, _MAX_CARDS)
    _require_range("n_versions", n_versions, 1, _MAX_VERSIONS)
    if n_features is not None:
        _require_range("n_features", n_features, 0, _MAX_FEATURES)
    _require_range("max_covers", max_covers, 0, _MAX_COVERS)
    _require_range("max_tokens", max_tokens, 1, _MAX_TOKENS)
    if n_pairs is not None:
        _require_range("n_pairs", n_pairs, 0, _MAX_PAIRS)
    _require_range("n_mandatory", n_mandatory, 0, _MAX_CARDS)
    if not budget_ratio >= 0 or budget_ratio == float("inf"):
        raise ValueError(f"budget_ratio must be a finite number >= 0, got {budget_ratio!r}")
    versions = []
    for i in range(n_versions):
        k = min(i, rng.randint(1, 2)) if i else 0
        versions.append({"id": f"v{i}", "parents": [f"v{j}" for j in rng.sample(range(i), k)]})
    ancestors = _strict_ancestors(versions)
    head = f"v{n_versions - 1}" if rng.random() < 0.5 else f"v{rng.randrange(n_versions)}"

    if n_features is None:
        n_features = max(1, n_cards)
    feature_ids = [f"f{i}" for i in range(n_features)]
    features = {fid: rng.randint(1, 100) for fid in feature_ids}
    group_ids = [f"g{i}" for i in range(max(1, n_cards // 3))]
    card_ids = [f"c{i}" for i in range(n_cards)]
    max_covers = min(max_covers, n_features)

    cards = []
    for i, cid in enumerate(card_ids):
        version = f"v{rng.randrange(n_versions)}"
        requires = []
        if n_cards > 1 and rng.random() < p_requires:
            requires = rng.sample(card_ids, min(rng.randint(1, 2), n_cards, _MAX_LINKS))
        supersedes = []
        if rng.random() < p_supersede:
            older = [c["id"] for c in cards if c["version"] in ancestors[version]]
            supersedes = rng.sample(older, min(len(older), rng.randint(1, 2)))
        card = {
            "id": cid,
            "version": version,
            "supersedes": supersedes,
            "requires": requires,
            "conflict_group": rng.choice(group_ids) if rng.random() < p_group else None,
            "tokens": rng.randint(1, max_tokens),
            "covers": rng.sample(feature_ids, rng.randint(0, max_covers)),
        }
        if rng.random() < 0.3:
            card["text"] = f"note {i}"
        cards.append(card)

    if n_pairs is None:
        n_pairs = n_cards // 2
    budget = min(_MAX_BUDGET, int(budget_ratio * sum(c["tokens"] for c in cards)))
    return {
        "versions": versions,
        "cards": cards,
        "features": features,
        "head": head,
        "budget": max(0, budget),
        "mandatory": rng.sample(card_ids, min(n_mandatory, n_cards)),
        "contradictions": _random_pairs(rng, card_ids, n_pairs),
    }


def max_request(rng, *, profile: bool = False) -> dict:
    """A valid request at the contract maxima.

    500 active cards, 96 versions in a chain with head at the tip, 1,024
    features, up to 64 covers per card, tokens up to 512, budget 8,192, and
    (unless ``profile``) 10,000 pairs, a 200-card requires chain, one requires
    cycle and 20 groups. With ``profile=True``: no requires, groups or pairs,
    one distinct feature per card.
    """
    n_cards = 500
    versions = [{"id": f"v{i}", "parents": [f"v{i - 1}"] if i else []} for i in range(96)]
    feature_ids = [f"f{i}" for i in range(1024)]
    features = {fid: rng.randint(1, 1000) for fid in feature_ids}
    card_ids = [f"c{i}" for i in range(n_cards)]
    distinct = rng.sample(feature_ids, n_cards)
    cards = []
    for i, cid in enumerate(card_ids):
        if profile:
            requires, group, covers = [], None, [distinct[i]]
        else:
            requires = []
            if i < 199:
                requires = [card_ids[i + 1]]  # cards 0..199 form a 200-card chain
            elif 200 <= i < 203:
                requires = [card_ids[200 + (i - 199) % 3]]  # cards 200..202 form a cycle
            group = f"g{rng.randrange(20)}" if i >= 203 and rng.random() < 0.5 else None
            covers = rng.sample(feature_ids, rng.randint(1, _MAX_COVERS))
        cards.append({
            "id": cid,
            "version": f"v{rng.randrange(96)}",
            "supersedes": [],
            "requires": requires,
            "conflict_group": group,
            "tokens": rng.randint(1, _MAX_TOKENS),
            "covers": covers,
        })
    if not profile:
        for j in range(20):  # every one of the 20 groups is used at least once
            cards[203 + j]["conflict_group"] = f"g{j}"
        cards[0]["tokens"] = _MAX_TOKENS
        cards[1]["covers"] = rng.sample(feature_ids, _MAX_COVERS)
    return {
        "versions": versions,
        "cards": cards,
        "features": features,
        "head": "v95",
        "budget": _MAX_BUDGET,
        "mandatory": [],
        "contradictions": [] if profile else _random_pairs(rng, card_ids, _MAX_PAIRS),
    }


def _fresh_names(rng, old_ids) -> dict:
    """A random bijection from ``old_ids`` to fresh, distinct, contract-valid identifiers."""
    used = set()
    mapping = {}
    for old in sorted(old_ids):
        while True:
            name = "".join(rng.choice(_ID_ALPHABET) for _ in range(rng.randint(1, 8)))
            if name not in used:
                break
        used.add(name)
        mapping[old] = name
    return mapping


def _shuffled(rng, items) -> list:
    out = list(items)
    rng.shuffle(out)
    return out


def permute_request(rng, request: dict) -> dict:
    """An equivalent request.

    Card, version, feature and group ids are renamed by a random bijection,
    every array is shuffled and pair orientation is flipped at random.
    """
    src = copy.deepcopy(request)
    vmap = _fresh_names(rng, [v["id"] for v in src["versions"]])
    cmap = _fresh_names(rng, [c["id"] for c in src["cards"]])
    fmap = _fresh_names(rng, src["features"])
    gmap = _fresh_names(rng, {c["conflict_group"] for c in src["cards"] if c["conflict_group"] is not None})

    versions = [{"id": vmap[v["id"]], "parents": _shuffled(rng, [vmap[p] for p in v["parents"]])}
                for v in _shuffled(rng, src["versions"])]
    cards = []
    for old in _shuffled(rng, src["cards"]):
        card = {
            "id": cmap[old["id"]],
            "version": vmap[old["version"]],
            "supersedes": _shuffled(rng, [cmap[x] for x in old["supersedes"]]),
            "requires": _shuffled(rng, [cmap[x] for x in old["requires"]]),
            "conflict_group": None if old["conflict_group"] is None else gmap[old["conflict_group"]],
            "tokens": old["tokens"],
            "covers": _shuffled(rng, [fmap[x] for x in old["covers"]]),
        }
        if "text" in old:
            card["text"] = old["text"]
        cards.append(card)
    pairs = []
    for left, right in _shuffled(rng, src["contradictions"]):
        pair = [cmap[left], cmap[right]]
        if rng.random() < 0.5:
            pair.reverse()
        pairs.append(pair)
    return {
        "versions": versions,
        "cards": cards,
        "features": {fmap[f]: src["features"][f] for f in _shuffled(rng, src["features"])},
        "head": vmap[src["head"]],
        "budget": src["budget"],
        "mandatory": _shuffled(rng, [cmap[x] for x in src["mandatory"]]),
        "contradictions": pairs,
    }
