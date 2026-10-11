"""Greedy construction plus simulated annealing over legal sets for large instances.

`solve_large` works on a `dcp_model.Problem`. It keeps the selected set as an integer bitmask
(for conflict and closure tests) next to per-feature cover counts and running token and utility
totals, so one move costs a few dozen list operations instead of a recomputation.
"""

import math
import random
import time

from dcp_model import is_legal

DEFAULT_SEED = 20261011
GUARD_MIN_S = 0.001       # the search stops this long before the deadline, or longer after a slow step
GUARD_MAX_S = 0.02
DROP_SAMPLE = 8           # selected cards sampled when a move has to shed tokens
ROUND_MOVES = 5000        # moves in one annealing round; a round restarts from the best set seen
T_HOT = 1.0               # start temperature of a round, in units of the mean utility per selected card
T_COLD = 0.03             # end temperature of a round, same unit
TOURNAMENT = True         # propose the less conflicting of two random cards
LAM_CYCLE = (1.0, 0.2)    # per-round multipliers of the token price
LAMBDA = 0.25             # token price, as a fraction of the greedy set's utility per token

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


def solve_large(p, deadline: float, seed: int = DEFAULT_SEED, *, max_moves=None) -> int:
    """Return a legal mask (at least p.mandatory). Runs until `deadline` (time.perf_counter() value) at the latest.

    `max_moves` (None or 0 means no limit) stops the search after that many loop iterations; it exists so that
    tools can compare search variants by work done instead of by wall time on a loaded host.
    """
    result = [p.mandatory, p.mandatory]  # [best seen, greedy result]
    try:
        _search(p, deadline, random.Random(seed), result, max_moves or 0)
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
    t_start = clock()
    try:
        for mode in (0, 2, 1):
            load(mandatory)
            refill(0, mode)
            if util > built_util:
                built_util, built_mask, built_mode = util, S, mode
                result[0] = result[1] = S
    except _Timeout:
        if util > built_util:
            result[0] = result[1] = S
        raise
    load(built_mask)
    LAST_STATS["greedy_mode"] = built_mode
    LAST_STATS["greedy_utility"] = util
    if not n_us or not p.usable & ~S:
        return

    # Simulated annealing over legal sets. One move inserts a random card with its closure, evicts
    # what conflicts with it (and what depends on the evicted cards) and sheds tokens when the budget
    # is exceeded. The energy is utility minus a small token price, so that at equal utility the
    # leaner set wins and room for further cards opens up. Rounds restart from the best set seen.
    best_util = util
    best_toks = toks
    best_mask = S
    unit = util / max(1, len(sel)) if util else 1.0
    lam = LAMBDA * util / toks if toks and util else 0.0
    t_hot = T_HOT * unit
    cool = (T_COLD / T_HOT) ** (1.0 / ROUND_MOVES)
    exp = math.exp
    moves = 0
    rounds = 0
    guard = GUARD_MIN_S

    def anneal(stop_moves, stop_time):
        nonlocal best_util, best_toks, best_mask, moves, rounds, guard
        temp = t_hot
        price = lam * LAM_CYCLE[rounds % len(LAM_CYCLE)]
        k = 0
        last = clock()
        while True:
            moves += 1
            now = clock()
            if now + guard >= stop_time:
                break
            # Leave room for the slowest step seen so far (bounded), so a long move cannot overrun.
            if now - last > guard:
                guard = min(GUARD_MAX_S, now - last)
            last = now
            if stop_moves and moves >= stop_moves:
                break
            k += 1
            if k >= ROUND_MOVES:
                k = 0
                rounds += 1
                temp = t_hot
                price = lam * LAM_CYCLE[rounds % len(LAM_CYCLE)]
                load(best_mask)
                journal.clear()
                refill(0, 0)
                if util > best_util:
                    best_util, best_toks, best_mask = util, toks, S
                    result[0] = S
            else:
                temp *= cool

            c = usable[int(rnd() * n_us)]
            if in_s[c]:
                continue
            evict = ccf[c] & S
            if evict and TOURNAMENT:
                # Of two random cards take the one that conflicts with fewer selected cards.
                c2 = usable[int(rnd() * n_us)]
                if not in_s[c2]:
                    evict2 = ccf[c2] & S
                    if evict2.bit_count() < evict.bit_count():
                        c, evict = c2, evict2
            target = closure[c]
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
            old_toks = toks
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
                        for x in _bits(group):
                            t += tok[x]
                            for f in cov[x]:
                                if cnt[f] == 1:
                                    lost += weights[f]
                    if t <= 0:
                        continue
                    if not worst or lost * worst_t < worst_l * t:
                        worst, worst_l, worst_t = group, lost, t
                if not worst:
                    ok = False
                    break
                for x in _bits(worst):
                    journal.append(~x)
                    drop(x)
            if ok:
                delta = util - old_util - price * (toks - old_toks)
                if delta < 0 and (delta < -30.0 * temp or rnd() >= exp(delta / temp)):
                    ok = False
            if ok:
                if util > best_util or (util == best_util and toks < best_toks):
                    best_util, best_toks, best_mask = util, toks, S
                    result[0] = S
            else:
                while journal:
                    x = journal.pop()
                    if x >= 0:
                        drop(x)
                    else:
                        add(~x)

    try:
        anneal(max_moves, deadline)
        if clock() + 4 * guard < deadline:
            load(best_mask)
            journal.clear()
            refill(0, 0)
            if util > best_util:
                result[0] = S
    finally:
        LAST_STATS["moves"] = moves
        LAST_STATS["perturbations"] = rounds
