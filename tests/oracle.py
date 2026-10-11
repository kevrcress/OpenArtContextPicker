"""Brute-force oracle: exact maximum utility by enumerating subsets of active cards.

Independent of every solver module. It takes the active set from ``checker``
and applies its own legality test (closures, conflicts, budget, mandatory)
during the enumeration.
"""

from __future__ import annotations

import checker


def best_set(request: dict, limit: int = 20) -> tuple:
    """Return ``(utility, sorted selected ids)`` of one maximum-utility legal set.

    Raises ValueError when there are more than ``limit`` active cards and
    LookupError when no legal set exists.
    """
    active = sorted(checker.active_cards(request))
    if len(active) > limit:
        raise ValueError(f"{len(active)} active cards exceed the oracle limit {limit}")
    by_id = {c["id"]: c for c in request["cards"]}
    active_set = set(active)

    # A card is usable only when its whole requires closure is active.
    closures = {}
    for cid in active:
        seen = set()
        stack = [cid]
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(by_id[cur]["requires"])
        closures[cid] = seen
    usable = [cid for cid in active if closures[cid] <= active_set]
    if any(cid not in usable for cid in request["mandatory"]):
        raise LookupError("a mandatory card cannot be selected")

    index = {cid: i for i, cid in enumerate(usable)}
    n = len(usable)
    need = [0] * n
    clash = [0] * n
    for cid, i in index.items():
        for dep in closures[cid]:
            need[i] |= 1 << index[dep]
    members = {}
    for cid, i in index.items():
        group = by_id[cid]["conflict_group"]
        if group is not None:
            members.setdefault(group, []).append(i)
    for group_members in members.values():
        for i in group_members:
            for j in group_members:
                if i != j:
                    clash[i] |= 1 << j
    for left, right in request["contradictions"]:
        if left in index and right in index:
            clash[index[left]] |= 1 << index[right]
            clash[index[right]] |= 1 << index[left]

    tokens = [by_id[cid]["tokens"] for cid in usable]
    covers = [frozenset(by_id[cid]["covers"]) for cid in usable]
    weights = request["features"]
    budget = request["budget"]
    must = 0
    for cid in request["mandatory"]:
        must |= 1 << index[cid]

    best_utility_seen = -1
    best_mask = 0
    # Depth-first include/exclude with an explicit stack. Pruning on conflicts
    # and budget is safe: both only get worse as cards are added.
    stack = [(0, 0, 0, 0, frozenset())]
    while stack:
        i, mask, required, spent, covered = stack.pop()
        if i == n:
            if required & ~mask or must & ~mask:
                continue
            utility = sum(weights[f] for f in covered)
            if utility > best_utility_seen:
                best_utility_seen = utility
                best_mask = mask
            continue
        stack.append((i + 1, mask, required, spent, covered))
        if not clash[i] & mask and spent + tokens[i] <= budget:
            stack.append((i + 1, mask | 1 << i, required | need[i], spent + tokens[i], covered | covers[i]))

    if best_utility_seen < 0:
        raise LookupError("no legal set exists")
    return best_utility_seen, [usable[i] for i in range(n) if best_mask >> i & 1]


def best_utility(request: dict, limit: int = 20) -> int:
    """Exhaustive maximum over all subsets of active cards.

    Raises ValueError when ``len(active) > limit`` and LookupError when no legal set exists.
    """
    return best_set(request, limit)[0]
