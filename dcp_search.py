"""Greedy construction plus iterated ejection-and-refill local search for large instances.

`solve_large` works on a `dcp_model.Problem`. It keeps the selected set as an integer bitmask
(for conflict and closure tests) next to per-feature cover counts and running token and utility
totals, so one move costs a few dozen list operations instead of a recomputation.
"""

import random
import time

from dcp_model import is_legal

DEFAULT_SEED = 20261011
CLOCK_EVERY = 1           # loop iterations between clock checks (a closure-heavy move can take over 1 ms)
DROP_SAMPLE = 8           # selected cards sampled when a move has to shed tokens
STALE_MIN = 120           # lower bound on moves without improvement before a perturbation
STALE_MAX = 600
PERTURB_MIN = 2
PERTURB_MAX = 5

# Filled by the last call; read by tools/tune_search.py. Not part of the solver contract.
LAST_STATS = {"moves": 0, "perturbations": 0, "greedy_utility": 0}


class _Timeout(Exception):
    """Raised inside the search when the deadline passes in the middle of a move."""


def _bits(mask: int) -> list:
    out = []
    while mask:
        low = mask & -mask
        out.append(low.bit_length() - 1)
        mask ^= low
    return out


def solve_large(p, deadline: float, seed: int = DEFAULT_SEED, *, max_moves: int = 0) -> int:
    """Return a legal mask (at least p.mandatory). Runs until `deadline` (time.perf_counter() value) at the latest.

    `max_moves` (0 means no limit) stops the search after that many loop iterations; it exists so that
    tools can compare search variants by work done instead of by wall time on a loaded host.
    """
    result = [p.mandatory, p.mandatory]  # [best seen, greedy result]
    try:
        _search(p, deadline, random.Random(seed), result, max_moves)
    except _Timeout:
        pass
    for mask in result:
        if is_legal(p, mask):
            return mask
    return p.mandatory


def _search(p, deadline: float, rng, result: list, max_moves: int = 0) -> None:
    clock = time.perf_counter
    rnd = rng.random
    n_bits = len(p.ids)
    budget = p.budget
    tok = p.tokens
    weights = p.feat_w
    closure = p.closure
    ccf = p.closure_conflict
    dependents = p.dependents
    mandatory = p.mandatory
    usable = _bits(p.usable)
    n_us = len(usable)
    LAST_STATS["moves"] = 0
    LAST_STATS["perturbations"] = 0
    LAST_STATS["greedy_utility"] = 0
    if clock() >= deadline:
        return

    bit = [1 << i for i in range(n_bits)]
    cov = [[f for f in _bits(p.cover[i]) if weights[f] > 0] for i in range(n_bits)]
    clos = [_bits(closure[i]) for i in range(n_bits)]
    single = [closure[i] == bit[i] for i in range(n_bits)]
    by_tok = sorted(usable, key=lambda i: (tok[i], i))

    cnt = [0] * len(weights)
    in_s = [False] * n_bits
    sel = []                  # selected cards, unordered
    pos = [-1] * n_bits       # position of a card in sel
    journal = []              # i for an add, ~i for a drop
    S = 0
    toks = 0
    util = 0

    def add(i):
        nonlocal S, toks, util
        S |= bit[i]
        in_s[i] = True
        pos[i] = len(sel)
        sel.append(i)
        toks += tok[i]
        for f in cov[i]:
            if not cnt[f]:
                util += weights[f]
            cnt[f] += 1

    def drop(i):
        nonlocal S, toks, util
        S ^= bit[i]
        in_s[i] = False
        k = pos[i]
        last = sel.pop()
        if last != i:
            sel[k] = last
            pos[last] = k
        pos[i] = -1
        toks -= tok[i]
        for f in cov[i]:
            cnt[f] -= 1
            if not cnt[f]:
                util -= weights[f]

    def load(mask):
        for i in _bits(S & ~mask):
            drop(i)
        for i in _bits(mask & ~S):
            add(i)

    def marginal(c):
        gain = 0
        cost = 0
        seen = set()
        for j in clos[c]:
            if not in_s[j]:
                cost += tok[j]
                for f in cov[j]:
                    if not cnt[f] and f not in seen:
                        seen.add(f)
                        gain += weights[f]
        return gain, cost

    def refill(banned, mode):
        # mode 0: gain per marginal token; 1: gain; 2: gain per (1 + addable cards the unit would block).
        while True:
            if clock() >= deadline:
                raise _Timeout
            rem = budget - toks
            free = 0
            if mode == 2:
                for c in by_tok:
                    if not in_s[c] and not ccf[c] & S:
                        free |= bit[c]
            best_c = -1
            best_g = 0
            best_t = 1
            for c in by_tok:
                t = tok[c]
                if t > rem:
                    break
                if in_s[c] or ccf[c] & S or banned & bit[c]:
                    continue
                if single[c]:
                    g = 0
                    for f in cov[c]:
                        if not cnt[f]:
                            g += weights[f]
                else:
                    if clock() >= deadline:
                        raise _Timeout
                    g, t = marginal(c)
                    if t > rem:
                        continue
                if g <= 0:
                    continue
                if mode != 1:
                    d = t if mode == 0 else 1 + (ccf[c] & free).bit_count()
                    lhs = g * best_t
                    rhs = best_g * d
                    if lhs > rhs or (lhs == rhs and best_c >= 0 and c < best_c):
                        best_c, best_g, best_t = c, g, d
                elif g > best_g or (g == best_g and (t < best_t or (t == best_t and c < best_c))):
                    best_c, best_g, best_t = c, g, t
            if best_c < 0:
                return
            for j in clos[best_c]:
                if not in_s[j]:
                    journal.append(j)
                    add(j)

    for i in _bits(mandatory):
        add(i)

    # Construction: three greedy rules (per token, per blocked card, plain gain); keep the best.
    built_util = -1
    built_mask = mandatory
    built_mode = 0
    starts = {}
    t_start = clock()
    try:
        for mode in (0, 2, 1):
            load(mandatory)
            refill(0, mode)
            starts[mode] = S
            if util > built_util:
                built_util, built_mask, built_mode = util, S, mode
                result[0] = result[1] = S
    except _Timeout:
        if util > built_util:
            result[0] = result[1] = S
        raise
    load(built_mask)
    g_util = util
    g_mask = S
    g_mode = 2 if built_mode == 2 else 0
    LAST_STATS["greedy_mode"] = built_mode
    LAST_STATS["greedy_utility"] = util
    if not n_us or not p.usable & ~S:
        return

    stale_limit = min(STALE_MAX, max(STALE_MIN, n_us))
    stale = 0
    moves = 0
    perturbations = 0
    try:
        # Portfolio: a slice from the per-token greedy, a slice from the per-blocked-card greedy, then
        # the rest of the time from the best set seen, with the refill rule that found it.
        for phase in range(3):
            if phase == 0:
                start_mask, ls_mode, frac = starts[0], 0, 0.25
            elif phase == 1:
                start_mask, ls_mode, frac = starts[2], 2, 0.5
            else:
                start_mask, ls_mode, frac = g_mask, g_mode, 1.0
            load(start_mask)
            best_util = util
            best_mask = S
            stale = 0
            phase_deadline = deadline if phase == 2 else t_start + (deadline - t_start) * frac
            phase_moves = int(max_moves * frac) if max_moves else 0
            while True:
                moves += 1
                if not moves % CLOCK_EVERY and clock() >= phase_deadline:
                    break
                if phase_moves and moves >= phase_moves:
                    break
                if stale > stale_limit:
                    # Perturbation: restart from the best set when the walk has fallen behind, then
                    # remove a few random units and refill without them.
                    stale = 0
                    perturbations += 1
                    if util < best_util:
                        load(best_mask)
                    banned = 0
                    for _ in range(PERTURB_MIN + int(rnd() * (PERTURB_MAX - PERTURB_MIN + 1))):
                        if not sel:
                            break
                        j = sel[int(rnd() * len(sel))]
                        group = dependents[j] & S
                        if group & mandatory:
                            continue
                        banned |= group
                        for k in _bits(group):
                            drop(k)
                    journal.clear()
                    refill(banned, ls_mode)
                    refill(0, ls_mode)
                    if util > best_util:
                        best_util = util
                        best_mask = S
                        if util > g_util:
                            g_util, g_mask, g_mode = util, S, ls_mode
                            result[0] = S
                    continue

                c = usable[int(rnd() * n_us)]
                if in_s[c]:
                    continue
                target = closure[c]
                evict = ccf[c] & S
                if evict:
                    if evict & mandatory:
                        continue
                    todo = evict
                    while todo:
                        low = todo & -todo
                        todo ^= low
                        more = dependents[low.bit_length() - 1] & S & ~evict
                        if more:
                            evict |= more
                            todo |= more
                    if evict & mandatory or evict & target:
                        continue
                old_util = util
                journal.clear()
                if evict:
                    for j in _bits(evict):
                        journal.append(~j)
                        drop(j)
                for j in clos[c]:
                    if not in_s[j]:
                        journal.append(j)
                        add(j)

                ok = True
                protect = target | mandatory
                while toks > budget:
                    # Shed the sampled unit with the least lost weight per freed token.
                    worst = 0
                    worst_l = 0
                    worst_t = 0
                    n_sel = len(sel)
                    for _ in range(DROP_SAMPLE):
                        j = sel[int(rnd() * n_sel)]
                        group = dependents[j] & S
                        if group & protect:
                            continue
                        if group == bit[j]:
                            t = tok[j]
                            lost = 0
                            for f in cov[j]:
                                if cnt[f] == 1:
                                    lost += weights[f]
                        else:
                            t = 0
                            lost = 0
                            for k in _bits(group):
                                t += tok[k]
                                for f in cov[k]:
                                    if cnt[f] == 1:
                                        lost += weights[f]
                        if t <= 0:
                            continue
                        if not worst or lost * worst_t < worst_l * t:
                            worst, worst_l, worst_t = group, lost, t
                    if not worst:
                        ok = False
                        break
                    for k in _bits(worst):
                        journal.append(~k)
                        drop(k)
                if ok:
                    refill(0, ls_mode)
                if ok and util >= old_util:
                    if util > old_util:
                        stale = 0
                    else:
                        stale += 1
                    if util > best_util:
                        best_util = util
                        best_mask = S
                        if util > g_util:
                            g_util, g_mask, g_mode = util, S, ls_mode
                            result[0] = S
                else:
                    stale += 1
                    while journal:
                        x = journal.pop()
                        if x >= 0:
                            drop(x)
                        else:
                            add(~x)
            if clock() >= deadline:
                break
    finally:
        LAST_STATS["moves"] = moves
        LAST_STATS["perturbations"] = perturbations
