"""Independent legality checker for director-context responses.

Written from ``director_context_contract.md`` only. Works on the raw request
dict with sets and dicts and imports nothing from the solver, so a solver bug
cannot be shared with the code that judges it.

The checker is only ever handed requests that satisfy the input contract.
"""

from __future__ import annotations

_OK_KEYS = {"status", "selected", "tokens", "covered", "utility"}
_REASON_KEYS = {"status", "reason"}
_CERT_KEYS = {"scale", "budget_price", "feature_prices"}
_MAX_SCALE = 1_000_000


def _is_int(value: object) -> bool:
    """True for a real integer; booleans are not integers."""
    return type(value) is int


def visible_versions(request: dict) -> set:
    """Head plus every transitive ancestor of head."""
    parents = {v["id"]: v["parents"] for v in request["versions"]}
    seen = {request["head"]}
    stack = [request["head"]]
    while stack:
        for parent in parents[stack.pop()]:
            if parent not in seen:
                seen.add(parent)
                stack.append(parent)
    return seen


def active_cards(request: dict) -> set:
    """Ids of visible cards that no visible card supersedes, directly or through a chain."""
    visible = visible_versions(request)
    by_id = {c["id"]: c for c in request["cards"]}
    visible_ids = {c["id"] for c in request["cards"] if c["version"] in visible}
    suppressed = set()
    stack = list(visible_ids)
    expanded = set()
    while stack:
        cid = stack.pop()
        if cid in expanded:
            continue
        expanded.add(cid)
        for older in by_id[cid]["supersedes"]:
            suppressed.add(older)
            stack.append(older)
    return visible_ids - suppressed


def requires_closure(request: dict, roots) -> set:
    """Every card reachable from ``roots`` through ``requires``, roots included."""
    by_id = {c["id"]: c for c in request["cards"]}
    seen = set()
    stack = list(roots)
    while stack:
        cid = stack.pop()
        if cid in seen:
            continue
        seen.add(cid)
        stack.extend(by_id[cid]["requires"])
    return seen


def legality_errors(request: dict, selected) -> list:
    """Violations of the six legal-set conditions for a collection of known card ids."""
    errors = []
    chosen = set(selected)
    by_id = {c["id"]: c for c in request["cards"]}
    active = active_cards(request)

    for cid in sorted(chosen - active):
        errors.append(f"condition 1: selected card {cid!r} is not active")
    for cid in request["mandatory"]:
        if cid not in chosen:
            errors.append(f"condition 2: mandatory card {cid!r} is not selected")
    for cid in sorted(requires_closure(request, chosen) - chosen):
        errors.append(f"condition 3: required card {cid!r} is not selected")

    groups = {}
    for cid in chosen:
        group = by_id[cid]["conflict_group"]
        if group is not None:
            groups.setdefault(group, []).append(cid)
    for group, members in sorted(groups.items()):
        if len(members) > 1:
            errors.append(f"condition 4: conflict group {group!r} has {sorted(members)}")

    for pair in request["contradictions"]:
        if pair[0] in chosen and pair[1] in chosen:
            errors.append(f"condition 5: contradiction pair {sorted(pair)} is selected")

    tokens = sum(by_id[cid]["tokens"] for cid in chosen)
    if tokens > request["budget"]:
        errors.append(f"condition 6: tokens {tokens} exceed budget {request['budget']}")
    return errors


def expected_feasible(request: dict) -> bool:
    """False when the mandatory closure is not itself a legal set."""
    closure = requires_closure(request, request["mandatory"])
    return not legality_errors(request, closure)


def response_for(request: dict, selected) -> dict:
    """An ``ok`` response with honestly recomputed totals for ``selected`` (no legality check)."""
    by_id = {c["id"]: c for c in request["cards"]}
    chosen = sorted(set(selected))
    covered = set()
    for cid in chosen:
        covered.update(by_id[cid]["covers"])
    return {
        "status": "ok",
        "selected": chosen,
        "tokens": sum(by_id[cid]["tokens"] for cid in chosen),
        "covered": sorted(covered),
        "utility": sum(request["features"][f] for f in covered),
    }


def _id_list_errors(name: str, value: object) -> list:
    if not isinstance(value, list) or any(type(x) is not str for x in value):
        return [f"{name} is not a list of strings"]
    errors = []
    if len(set(value)) != len(value):
        errors.append(f"{name} has repeated ids")
    if sorted(value) != value:
        errors.append(f"{name} is not in ascending ASCII order")
    return errors


def _reason_shape_errors(response: dict) -> list:
    errors = []
    if set(response) != _REASON_KEYS:
        errors.append(f"keys {sorted(response)} are not exactly {sorted(_REASON_KEYS)}")
    reason = response.get("reason")
    if type(reason) is not str or not reason:
        errors.append("reason is not a nonempty string")
    return errors


def certificate_errors(request: dict, certificate: object) -> list:
    """Shape and range violations of a certificate; every message starts with ``certificate:``."""
    if not isinstance(certificate, dict):
        return ["certificate: not an object"]
    if set(certificate) != _CERT_KEYS:
        return [f"certificate: keys {sorted(certificate)} are not exactly {sorted(_CERT_KEYS)}"]
    errors = []
    features = request["features"]
    scale = certificate["scale"]
    price = certificate["budget_price"]
    prices = certificate["feature_prices"]
    scale_ok = _is_int(scale) and 1 <= scale <= _MAX_SCALE
    if not scale_ok:
        errors.append("certificate: scale is not an integer in 1..1000000")
    if not _is_int(price) or price < 0:
        errors.append("certificate: budget_price is not a nonnegative integer")
    elif scale_ok and price > scale * sum(features.values()):
        errors.append("certificate: budget_price exceeds scale times total feature weight")
    if not isinstance(prices, dict):
        errors.append("certificate: feature_prices is not an object")
        return errors
    if set(prices) != set(features):
        errors.append("certificate: feature_prices keys are not exactly the feature ids")
    for fid in sorted(set(prices) & set(features)):
        value = prices[fid]
        if not _is_int(value) or value < 0:
            errors.append(f"certificate: price of {fid!r} is not a nonnegative integer")
        elif scale_ok and value > features[fid] * scale:
            errors.append(f"certificate: price of {fid!r} exceeds weight times scale")
    return errors


def check_response(request: dict, response: dict, *, request_valid: bool = True) -> list:
    """Return a list of error strings; empty means the response is correct in form and legal.

    With ``request_valid=False`` the request is known to break the input contract
    and the only acceptable response is the exact ``invalid`` shape. Certificate
    problems are reported with a ``certificate:`` prefix because the contract
    judges them apart from the core fields.
    """
    if not isinstance(response, dict):
        return ["response is not a JSON object"]
    status = response.get("status")
    if type(status) is not str or status not in ("ok", "invalid", "infeasible"):
        return [f"status {status!r} is not one of ok, invalid, infeasible"]

    if not request_valid:
        errors = [] if status == "invalid" else [f"status {status!r} on an invalid request"]
        if status != "ok":
            errors.extend(_reason_shape_errors(response))
        return errors
    if status == "invalid":
        return ["status 'invalid' on a valid request"] + _reason_shape_errors(response)

    feasible = expected_feasible(request)
    if status == "infeasible":
        errors = _reason_shape_errors(response)
        if feasible:
            errors.append("status 'infeasible' but the mandatory closure is a legal set")
        return errors

    errors = []
    if not feasible:
        errors.append("status 'ok' but the mandatory closure is not a legal set")
    keys = set(response)
    for key in sorted(_OK_KEYS - keys):
        errors.append(f"missing key {key!r}")
    for key in sorted(keys - _OK_KEYS - {"certificate"}):
        errors.append(f"unexpected key {key!r}")
    if _OK_KEYS - keys:
        return errors

    selected = response["selected"]
    selected_errors = _id_list_errors("selected", selected)
    errors.extend(selected_errors)
    errors.extend(_id_list_errors("covered", response["covered"]))
    for name in ("tokens", "utility"):
        if not _is_int(response[name]) or response[name] < 0:
            errors.append(f"{name} is not a nonnegative integer")
    if selected_errors and not isinstance(selected, list):
        return errors
    if selected_errors and any(type(x) is not str for x in selected):
        return errors

    by_id = {c["id"]: c for c in request["cards"]}
    unknown = sorted(set(selected) - set(by_id))
    if unknown:
        errors.append(f"condition 1: selected ids {unknown} are not cards")
        return errors

    errors.extend(legality_errors(request, selected))
    truth = response_for(request, selected)
    for name in ("tokens", "covered", "utility"):
        if response[name] != truth[name] or type(response[name]) is not type(truth[name]):
            errors.append(f"{name} is {response[name]!r}, recomputed {truth[name]!r}")

    if "certificate" in response:
        errors.extend(certificate_errors(request, response["certificate"]))
    return errors


def certificate_bound(request: dict, certificate: dict) -> tuple:
    """``(U, s)`` by the contract formula, exact integers, summing over active cards."""
    scale = certificate["scale"]
    price = certificate["budget_price"]
    prices = certificate["feature_prices"]
    active = active_cards(request)
    total = request["budget"] * price
    for card in request["cards"]:
        if card["id"] in active:
            gain = sum(prices[f] for f in card["covers"]) - price * card["tokens"]
            if gain > 0:
                total += gain
    for fid, weight in request["features"].items():
        total += weight * scale - prices[fid]
    return total, scale


def is_certificate_profile(request: dict) -> bool:
    """Contract tight-gap profile: no requires, groups or pairs; active covers are disjoint."""
    if request["contradictions"]:
        return False
    for card in request["cards"]:
        if card["requires"] or card["conflict_group"] is not None:
            return False
    active = active_cards(request)
    seen = set()
    for card in request["cards"]:
        if card["id"] not in active:
            continue
        for fid in card["covers"]:
            if fid in seen:
                return False
            seen.add(fid)
    return True
