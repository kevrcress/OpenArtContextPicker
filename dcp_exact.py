"""Exact depth-first branch and bound over the usable cards of a ``dcp_model.Problem``.

Exact for every problem it is given enough time for; the pipeline relies on it
for requests with at most 24 active cards and uses it as an anytime improver
(with an incumbent and a short deadline) on mid-size requests.
"""

from __future__ import annotations

import time

import dcp_model

_CACHE_LIMIT = 300_000


def _bits(mask: int) -> list:
    """Indices of the set bits of ``mask``, ascending."""
    out = []
    while mask:
        low = mask & -mask
        out.append(low.bit_length() - 1)
        mask ^= low
    return out


def _greedy(p, order: list, cover: list, weight, deadline: float) -> int:
    """Closure-aware greedy seed: repeatedly add the closure with the best gain per new token."""
    selected = p.mandatory
    spent = dcp_model.mask_tokens(p, selected)
    covered = 0
    tokens = p.tokens
    pool = list(order)
    while pool:
        if time.perf_counter() >= deadline:
            break
        best_key = None
        best_card = -1
        keep = []
        for c in pool:
            if selected >> c & 1 or p.closure_conflict[c] & selected:
                continue
            cost = sum(tokens[j] for j in _bits(p.closure[c] & ~selected))
            if spent + cost > p.budget:
                continue
            gain = weight(cover[c] & ~covered)
            keep.append(c)
            if gain <= 0:
                continue
            key = (gain / cost if cost else float("inf"), gain)
            if best_key is None or key > best_key:
                best_key = key
                best_card = c
        if best_card < 0:
            break
        selected |= p.closure[best_card]
        spent = dcp_model.mask_tokens(p, selected)
        covered |= cover[best_card]
        pool = keep
    return selected


def solve_exact(p, deadline: float, incumbent: int | None = None) -> tuple:
    """Return ``(mask, proven)``.

    ``mask`` is always a legal set (at least ``p.mandatory``). ``proven`` is
    True when the search space was exhausted before ``deadline`` (a
    ``time.perf_counter()`` value); then ``mask`` has the maximum utility.
    """
    budget = p.budget
    tokens = p.tokens
    feat_w = p.feat_w
    closure = p.closure
    dependents = p.dependents
    mandatory = p.mandatory
    order = _bits(p.usable)

    # Only features with positive weight that the mandatory set leaves open can
    # change the objective; every mask below is restricted to them and utility
    # is counted relative to the mandatory set.
    base_cover = dcp_model.mask_cover(p, mandatory)
    relevant = 0
    for f, w in enumerate(feat_w):
        if w > 0:
            relevant |= 1 << f
    relevant &= ~base_cover
    cover = [0] * len(tokens)
    closure_cover = [0] * len(tokens)
    for c in order:
        cover[c] = p.cover[c] & relevant
        closure_cover[c] = p.closure_cover[c] & relevant
    closure_conflict = p.closure_conflict

    cache = {0: 0}

    def weight(fmask: int) -> int:
        value = cache.get(fmask)
        if value is None:
            value = 0
            rest = fmask
            while rest:
                low = rest & -rest
                value += feat_w[low.bit_length() - 1]
                rest ^= low
            if len(cache) > _CACHE_LIMIT:
                cache.clear()
            cache[fmask] = value
        return value

    best_mask = mandatory
    best = 0
    if incumbent is not None and dcp_model.is_legal(p, incumbent):
        value = weight(dcp_model.mask_cover(p, incumbent) & relevant)
        if value > best:
            best, best_mask = value, incumbent
    if incumbent is None or len(order) <= 64:
        seed = _greedy(p, order, closure_cover, weight, deadline)
        value = weight(dcp_model.mask_cover(p, seed) & relevant)
        if value > best:
            best, best_mask = value, seed
    if not order:
        return best_mask, True

    # Byte tables for the weight of a wide feature mask (bound (a)), built on first use.
    n_bytes = (relevant.bit_length() + 7) // 8
    tables = []

    def wide_weight(fmask: int) -> int:
        if not tables:
            n_feat = len(feat_w)
            for position in range(n_bytes):
                table = [0] * 256
                base = position * 8
                for byte in range(1, 256):
                    low = byte & -byte
                    f = base + low.bit_length() - 1
                    table[byte] = table[byte ^ low] + (feat_w[f] if f < n_feat else 0)
                tables.append(table)
        value = 0
        for table, byte in zip(tables, fmask.to_bytes(n_bytes, "little")):
            value += table[byte]
        return value

    base_tokens = dcp_model.mask_tokens(p, mandatory)
    perf_counter = time.perf_counter
    cache_get = cache.get
    inf = float("inf")
    work = 4096  # read the clock at the first node
    seen_a = tried_a = hits_a = 0
    # Node: (selected, excluded, tokens spent, covered relevant features, utility, candidates, stale).
    # candidates holds (card, gain) with gain measured before the features in ``stale`` were covered.
    stack = [(mandatory, 0, base_tokens, 0, 0, [(c, weight(cover[c])) for c in order], 0)]
    while stack:
        selected, excluded, spent, covered, utility, candidates, stale = stack.pop()
        # The clock is read about once per 4,096 card visits, so the overshoot
        # stays near a millisecond whether a node holds 24 candidates or 500.
        work += len(candidates) + 16
        if work >= 4096:
            work = 0
            if perf_counter() >= deadline:
                return best_mask, False
        if utility > best:
            best, best_mask = utility, selected
        room = budget - spent
        blocked = selected | excluded
        items = []
        total = 0
        for c, gain in candidates:
            # Every filter here is permanent below this node: the selected and
            # excluded sets and the covered features only grow, the room only shrinks.
            if blocked >> c & 1 or closure_conflict[c] & selected or tokens[c] > room:
                continue
            if stale:
                lost_mask = cover[c] & stale
                if lost_mask:
                    lost = cache_get(lost_mask)
                    if lost is None:
                        lost = weight(lost_mask)
                    gain -= lost
            if gain <= 0:
                continue
            cost = tokens[c]
            items.append((gain / cost if cost else inf, c, gain))
            total += gain
        if utility + total <= best:
            continue
        # Bound (b): fractional knapsack over the eligible cards' own gains and own tokens.
        items.sort(reverse=True)
        bound = utility
        left = room
        for _, c, gain in items:
            cost = tokens[c]
            if cost <= left:
                left -= cost
                bound += gain
            else:
                bound += gain * left // cost
                break
        if bound <= best:
            continue
        # Bound (a): nothing beyond the features the eligible cards can still reach.
        # It is costly on wide masks, so while it rarely prunes it runs on one node in 16
        # (skipping a bound never costs exactness).
        seen_a += 1
        if hits_a * 16 >= tried_a or not seen_a & 15:
            tried_a += 1
            union = 0
            for item in items:
                union |= cover[item[1]]
            if utility + wide_weight(union & ~covered) <= best:
                hits_a += 1
                continue

        branch = items[0][1]
        rest = [(item[1], item[2]) for item in items[1:]]
        # Exclude: nothing that needs the branch card can be taken either.
        stack.append((selected, excluded | dependents[branch], spent, covered, utility, rest, 0))
        # Include the whole closure when it avoids the excluded cards and fits.
        need = closure[branch]
        if need & excluded:
            continue
        fresh = need & ~selected
        if fresh == 1 << branch:
            cost = tokens[branch]
        else:
            cost = 0
            for j in _bits(fresh):
                cost += tokens[j]
        if cost > room:
            continue
        gain_mask = closure_cover[branch] & ~covered
        stack.append((selected | need, excluded, spent + cost, covered | gain_mask,
                      utility + weight(gain_mask), rest, gain_mask))
    return best_mask, True
