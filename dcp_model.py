"""Active set, requirement closures, conflict masks and legality for a director context request.

Input is a request dict that has already passed strict validation. Cards are mapped to bits of
Python ints: bit ``i`` is ``Problem.ids[i]``, the active card ids in ascending order. Nothing here
recurses: version ancestry, supersession chains and requirement closures all use explicit stacks.
"""

from __future__ import annotations

from dataclasses import dataclass


class Infeasible(Exception):
    """str(exc) is a nonempty ASCII reason. Raised only when the mandatory closure is not a legal set."""


@dataclass(frozen=True)
class Problem:
    """A request reduced to bitmasks over its active cards."""

    budget: int
    n: int  # the contract's active-card count (visible, not superseded), before usability
    ids: tuple  # active card ids sorted ascending; bit i <-> ids[i]
    tokens: tuple  # tokens[i]
    feat_ids: tuple  # ALL feature ids of the request, sorted ascending; feature index f
    feat_w: tuple  # feat_w[f]
    cover: tuple  # cover[i]: int bitmask over feature indices
    closure: tuple  # closure[i]: transitive requires closure incl. i; 0 if it leaves the active set
    conflict: tuple  # conflict[i]: active cards that cannot be selected with i; never includes i
    closure_tokens: tuple  # token sum of closure[i]
    closure_cover: tuple  # OR of cover[j] for j in closure[i]
    closure_conflict: tuple  # OR of conflict[j] for j in closure[i]
    dependents: tuple  # dependents[i]: active cards j with closure[j] containing i (includes i)
    mandatory: int  # bitmask: union of closures of mandatory cards; a legal set by construction
    usable: int  # cards i NOT in mandatory whose closure can be added to the mandatory set legally


def _visible_versions(req: dict) -> set:
    """Return the head version and all of its transitive ancestors."""
    parents = {v["id"]: v["parents"] for v in req["versions"]}
    seen = {req["head"]}
    stack = [req["head"]]
    while stack:
        for parent in parents[stack.pop()]:
            if parent not in seen:
                seen.add(parent)
                stack.append(parent)
    return seen


def _active_ids(req: dict) -> list:
    """Return the visible cards that no visible card supersedes, directly or through a chain."""
    visible_versions = _visible_versions(req)
    cards = req["cards"]
    supersedes = {c["id"]: c["supersedes"] for c in cards}
    visible = [c["id"] for c in cards if c["version"] in visible_versions]
    superseded = set()
    stack = []
    for cid in visible:
        for old in supersedes[cid]:
            if old not in superseded:
                superseded.add(old)
                stack.append(old)
    while stack:
        for old in supersedes[stack.pop()]:
            if old not in superseded:
                superseded.add(old)
                stack.append(old)
    return sorted(cid for cid in visible if cid not in superseded)


def _closures(order: list, requires: dict, bit_of: dict, cover: list, conflict: list) -> tuple:
    """Compute per-card closure, closure cover and closure conflict masks.

    Runs an iterative Tarjan over the ``requires`` graph of ALL cards. Components come out sinks
    first, so each component ORs its own members with the finished components it points at. A
    component is dead when it contains or reaches a card that is not active.

    Returns:
        Three dicts keyed by card id: closure mask (0 when dead), cover mask, conflict mask.
    """
    index = {}
    low = {}
    on_stack = set()
    scc_stack = []
    comp_of = {}
    comp_mask = []
    comp_dead = []
    comp_cover = []
    comp_conflict = []
    counter = 0
    for root in order:
        if root in index:
            continue
        index[root] = low[root] = counter
        counter += 1
        scc_stack.append(root)
        on_stack.add(root)
        work = [(root, iter(requires[root]))]
        while work:
            node, edges = work[-1]
            descended = False
            for nxt in edges:
                if nxt not in index:
                    index[nxt] = low[nxt] = counter
                    counter += 1
                    scc_stack.append(nxt)
                    on_stack.add(nxt)
                    work.append((nxt, iter(requires[nxt])))
                    descended = True
                    break
                if nxt in on_stack and index[nxt] < low[node]:
                    low[node] = index[nxt]
            if descended:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                if low[node] < low[parent]:
                    low[parent] = low[node]
            if low[node] != index[node]:
                continue
            members = []
            while True:
                member = scc_stack.pop()
                on_stack.discard(member)
                members.append(member)
                if member == node:
                    break
            comp = len(comp_mask)
            for member in members:
                comp_of[member] = comp
            mask = 0
            dead = False
            cov = 0
            con = 0
            for member in members:
                bit = bit_of.get(member)
                if bit is None:
                    dead = True
                else:
                    mask |= 1 << bit
                    cov |= cover[bit]
                    con |= conflict[bit]
                for nxt in requires[member]:
                    other = comp_of[nxt]
                    if other != comp:
                        mask |= comp_mask[other]
                        cov |= comp_cover[other]
                        con |= comp_conflict[other]
                        dead = dead or comp_dead[other]
            comp_mask.append(mask)
            comp_dead.append(dead)
            comp_cover.append(cov)
            comp_conflict.append(con)
    closure = {}
    closure_cover = {}
    closure_conflict = {}
    for cid in order:
        comp = comp_of[cid]
        if comp_dead[comp]:
            closure[cid] = closure_cover[cid] = closure_conflict[cid] = 0
        else:
            closure[cid] = comp_mask[comp]
            closure_cover[cid] = comp_cover[comp]
            closure_conflict[cid] = comp_conflict[comp]
    return closure, closure_cover, closure_conflict


def _sum_bits(values: tuple, mask: int) -> int:
    """Sum ``values[i]`` over the set bits ``i`` of ``mask``."""
    total = 0
    while mask:
        low = mask & -mask
        total += values[low.bit_length() - 1]
        mask ^= low
    return total


def build_problem(req: dict) -> Problem:
    """Reduce a validated request to a ``Problem``.

    Raises:
        Infeasible: the mandatory closure is not a legal set.
    """
    cards = req["cards"]
    by_id = {c["id"]: c for c in cards}
    ids = tuple(_active_ids(req))
    n = len(ids)
    bit_of = {cid: i for i, cid in enumerate(ids)}
    budget = req["budget"]

    feat_ids = tuple(sorted(req["features"]))
    feat_w = tuple(req["features"][f] for f in feat_ids)
    feat_bit = {f: 1 << k for k, f in enumerate(feat_ids)}

    tokens = tuple(by_id[cid]["tokens"] for cid in ids)
    cover = []
    groups = {}
    for i, cid in enumerate(ids):
        card = by_id[cid]
        fmask = 0
        for feat in card["covers"]:
            fmask |= feat_bit[feat]
        cover.append(fmask)
        group = card["conflict_group"]
        if group is not None:
            groups[group] = groups.get(group, 0) | (1 << i)

    conflict = [0] * n
    for i, cid in enumerate(ids):
        group = by_id[cid]["conflict_group"]
        if group is not None:
            conflict[i] = groups[group] & ~(1 << i)
    for a, b in req["contradictions"]:
        ia = bit_of.get(a)
        ib = bit_of.get(b)
        if ia is not None and ib is not None:
            conflict[ia] |= 1 << ib
            conflict[ib] |= 1 << ia

    requires = {c["id"]: c["requires"] for c in cards}
    clo, clo_cover, clo_conflict = _closures(list(ids), requires, bit_of, cover, conflict)
    closure = tuple(clo[cid] for cid in ids)
    closure_cover = tuple(clo_cover[cid] for cid in ids)
    closure_conflict = tuple(clo_conflict[cid] for cid in ids)

    dependents = [1 << i for i in range(n)]
    closure_tokens = [0] * n
    token_memo = {}
    for j in range(n):
        mask = closure[j]
        if not mask:
            continue
        bit_j = 1 << j
        total = token_memo.get(mask)
        if total is None:
            total = 0
            walk = mask
            while walk:
                low = walk & -walk
                i = low.bit_length() - 1
                total += tokens[i]
                dependents[i] |= bit_j
                walk ^= low
            token_memo[mask] = total
        else:
            walk = mask
            while walk:
                low = walk & -walk
                dependents[low.bit_length() - 1] |= bit_j
                walk ^= low
        closure_tokens[j] = total

    mandatory = 0
    mandatory_conflict = 0
    for cid in req["mandatory"]:
        i = bit_of.get(cid)
        if i is None:
            raise Infeasible("a mandatory card is not active from the head version")
        if not closure[i]:
            raise Infeasible("a mandatory card requires a card that is not active")
        mandatory |= closure[i]
        mandatory_conflict |= closure_conflict[i]
    if mandatory_conflict & mandatory:
        raise Infeasible("the mandatory closure contains a conflict group clash or a contradiction pair")
    mandatory_tokens = _sum_bits(tokens, mandatory)
    if mandatory_tokens > budget:
        raise Infeasible("the mandatory closure exceeds the token budget")

    usable = 0
    for i in range(n):
        mask = closure[i]
        if not mask or (mandatory >> i) & 1:
            continue
        blocked = closure_conflict[i]
        if blocked & mask or blocked & mandatory:
            continue
        total = closure_tokens[i] + mandatory_tokens
        shared = mask & mandatory
        if shared:
            total -= _sum_bits(tokens, shared)
        if total <= budget:
            usable |= 1 << i

    return Problem(
        budget=budget,
        n=n,
        ids=ids,
        tokens=tokens,
        feat_ids=feat_ids,
        feat_w=feat_w,
        cover=tuple(cover),
        closure=closure,
        conflict=tuple(conflict),
        closure_tokens=tuple(closure_tokens),
        closure_cover=closure_cover,
        closure_conflict=closure_conflict,
        dependents=tuple(dependents),
        mandatory=mandatory,
        usable=usable,
    )


def mask_tokens(p: Problem, mask: int) -> int:
    """Return the token sum of the distinct cards in ``mask``."""
    return _sum_bits(p.tokens, mask)


def mask_cover(p: Problem, mask: int) -> int:
    """Return the feature bitmask covered by the cards in ``mask``."""
    cover = p.cover
    fmask = 0
    while mask:
        low = mask & -mask
        fmask |= cover[low.bit_length() - 1]
        mask ^= low
    return fmask


def cover_weight(p: Problem, fmask: int) -> int:
    """Return the utility of a feature bitmask: each covered feature's weight counted once."""
    return _sum_bits(p.feat_w, fmask)


def is_legal(p: Problem, mask: int) -> bool:
    """Return True when ``mask`` satisfies all six contract conditions for a selected set."""
    if mask < 0 or mask >> p.n:
        return False
    if mask & p.mandatory != p.mandatory:
        return False
    closure = p.closure
    conflict = p.conflict
    tokens = p.tokens
    total = 0
    walk = mask
    while walk:
        low = walk & -walk
        i = low.bit_length() - 1
        need = closure[i]
        if not need or need & ~mask or conflict[i] & mask:
            return False
        total += tokens[i]
        walk ^= low
    return total <= p.budget


def mask_ids(p: Problem, mask: int) -> list:
    """Return the selected card ids of ``mask`` in ascending order."""
    ids = p.ids
    out = []
    while mask:
        low = mask & -mask
        out.append(ids[low.bit_length() - 1])
        mask ^= low
    return out


def fmask_ids(p: Problem, fmask: int) -> list:
    """Return the covered feature ids of ``fmask`` in ascending order."""
    feat_ids = p.feat_ids
    out = []
    while fmask:
        low = fmask & -fmask
        out.append(feat_ids[low.bit_length() - 1])
        fmask ^= low
    return out
