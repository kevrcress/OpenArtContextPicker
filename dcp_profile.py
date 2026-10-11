"""Exact knapsack and utility upper-bound certificate for the contract's tight-gap profile.

Under the profile no card has a requirement or a conflict group, there are no
contradiction pairs, and no feature is covered by two active cards. A card's
value is then additive, so the selection problem is a 0/1 knapsack with the
mandatory cards forced.
"""

from __future__ import annotations

import time

from dcp_model import Problem, cover_weight, mask_cover, mask_tokens

_MAX_SCALE = 1_000_000
_PROJECT_EVERY = 16  # items between two projections of the remaining run time


def profile_applies(req: dict, p: Problem) -> bool:
    """Return True when ``req`` is in the contract's tight-gap profile.

    Every card of the request (active or not) has no requirement and no conflict
    group, there are no contradiction pairs, and no feature is covered by more
    than one ACTIVE card.
    """
    if req["contradictions"]:
        return False
    for card in req["cards"]:
        if card["requires"] or card["conflict_group"] is not None:
            return False
    seen = 0
    for fmask in p.cover:
        if fmask & seen:
            return False
        seen |= fmask
    return True


def solve_profile(p: Problem, deadline: float) -> int | None:
    """Return an optimal legal mask for a profile problem, or None when ``deadline`` would be exceeded.

    ``deadline`` is a ``time.perf_counter()`` value. The caller guarantees
    ``profile_applies``; the result always contains ``p.mandatory``.
    """
    clock = time.perf_counter
    capacity = p.budget - mask_tokens(p, p.mandatory)
    items = []
    walk = p.usable
    while walk:
        low = walk & -walk
        i = low.bit_length() - 1
        walk ^= low
        value = cover_weight(p, p.cover[i])
        if value > 0 and p.tokens[i] <= capacity:
            items.append((i, p.tokens[i], value))
    if capacity < 0 or clock() >= deadline:
        return None

    width = capacity + 1
    best = [0] * width  # best[c]: largest value of the items seen so far within c tokens
    rows = []  # rows[k][c - w]: 1 when item k is taken at capacity c
    started = clock()
    for k, (_, weight, value) in enumerate(items):
        if k % _PROJECT_EVERY == 0:
            now = clock()
            if now >= deadline:
                return None
            if k and now + (now - started) * (len(items) - k) / k >= deadline:
                return None
        old = best[weight:]
        new = [b + value for b in best[:width - weight]]
        rows.append(bytes([a > b for a, b in zip(new, old)]))
        best[weight:] = [a if a > b else b for a, b in zip(new, old)]
    if clock() >= deadline:
        return None

    mask = p.mandatory
    left = capacity
    for k in range(len(items) - 1, -1, -1):
        i, weight, _ = items[k]
        if left >= weight and rows[k][left - weight]:
            mask |= 1 << i
            left -= weight
    return mask


def _bound(p: Problem, values: list, scale: int, price: int) -> int:
    """Return the contract's ``U`` for ``feature_prices[f] = weight * scale`` and ``budget_price = price``."""
    total = p.budget * price
    tokens = p.tokens
    for i, value in enumerate(values):
        gain = value * scale - price * tokens[i]
        if gain > 0:
            total += gain
    return total  # the feature term is zero: every price equals weight * scale


def build_certificate(p: Problem, mask: int) -> dict | None:
    """Return a contract certificate with ``100 * U <= 105 * utility * scale`` for ``mask``, or None.

    Feature prices are ``weight * scale``; the budget price is the value per
    token of the fractional-greedy break card (or a neighbor), which is where
    the linear relaxation's dual is smallest.
    """
    values = [cover_weight(p, fmask) for fmask in p.cover]  # every active card, usable or not
    order = sorted(
        (i for i in range(p.n) if values[i] > 0 and p.tokens[i] > 0),
        key=lambda i: (-values[i] / p.tokens[i], i),
    )
    candidates = [(1, 0)]
    used = 0
    for pos, i in enumerate(order):
        used += p.tokens[i]
        if used > p.budget:
            for near in (pos - 1, pos, pos + 1):
                if 0 <= near < len(order):
                    candidates.append((p.tokens[order[near]], values[order[near]]))
            break

    weight_sum = sum(p.feat_w)
    best = None
    for scale, price in dict.fromkeys(candidates):
        if not 1 <= scale <= _MAX_SCALE or not 0 <= price <= scale * weight_sum:
            continue
        bound = _bound(p, values, scale, price)
        if best is None or bound * best[1] < best[0] * scale:
            best = (bound, scale, price)
    if best is None:
        return None
    bound, scale, price = best
    utility = cover_weight(p, mask_cover(p, mask))
    if 100 * bound > 105 * utility * scale:
        return None
    return {
        "scale": scale,
        "budget_price": price,
        "feature_prices": {fid: weight * scale for fid, weight in zip(p.feat_ids, p.feat_w)},
    }
