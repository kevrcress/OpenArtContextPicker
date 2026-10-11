"""Dispatch for one director context request: validate, build the model, pick a solver, answer.

``run`` never raises. Deadlines are ``time.perf_counter()`` values measured from ``t0``, the
moment the process started. After the model exists every failure path still answers ``ok`` with
a legal set: the best legal mask found so far, and at least the mandatory closure.
"""

from __future__ import annotations

import sys
import time
import traceback

import dcp_exact
import dcp_model
import dcp_profile
import dcp_search
import dcp_validate

EXACT_MAX_ACTIVE = 24
EXACT_DEADLINE_S = 3.5  # seconds after process start
LARGE_DEADLINE_S = 2.5  # seconds after process start; chosen for time safety in the 2-CPU container
MID_EXACT_MAX_ACTIVE = 64  # above 24 and up to this, the exact search runs after the heuristic
MID_SEARCH_DEADLINE_S = 1.0  # heuristic share for 25..64 active cards

# Facts about the last call of ``run``, for the one-line stderr diagnostic of the CLI.
LAST_DIAG = {"method": "none", "active": 0, "proven": False}


def _utility(p, mask: int) -> int:
    return dcp_model.cover_weight(p, dcp_model.mask_cover(p, mask))


def _report(stage: str) -> None:
    """Write the current exception to stderr; diagnostics must never break the answer."""
    try:
        sys.stderr.write(f"dcp_pipeline: {stage} failed\n{traceback.format_exc()}")
    except Exception:  # noqa: BLE001
        pass


def _solve(req: dict, p, t0: float) -> tuple:
    """Return ``(mask, method, proven, in_profile)``; ``mask`` is legal, at least ``p.mandatory``."""
    best = p.mandatory
    method = "mandatory"
    proven = False
    in_profile = False

    def keep(mask) -> bool:
        nonlocal best
        if type(mask) is int and dcp_model.is_legal(p, mask) and _utility(p, mask) >= _utility(p, best):
            best = mask
            return True
        return False

    try:
        in_profile = dcp_profile.profile_applies(req, p)
    except Exception:  # noqa: BLE001
        _report("profile_applies")
    if in_profile:
        try:
            mask = dcp_profile.solve_profile(p, t0 + LARGE_DEADLINE_S)
            if mask is not None and keep(mask):
                return best, "profile", True, True
        except Exception:  # noqa: BLE001
            _report("solve_profile")

    if p.n <= EXACT_MAX_ACTIVE:
        try:
            mask, proven = dcp_exact.solve_exact(p, t0 + EXACT_DEADLINE_S)
            proven = keep(mask) and bool(proven)
            method = "exact"
        except Exception:  # noqa: BLE001
            proven = False
            _report("solve_exact")
        return best, method, proven, in_profile

    mid = p.n <= MID_EXACT_MAX_ACTIVE
    try:
        keep(dcp_search.solve_large(p, t0 + (MID_SEARCH_DEADLINE_S if mid else LARGE_DEADLINE_S)))
        method = "search"
    except Exception:  # noqa: BLE001
        _report("solve_large")
    if mid:
        try:
            mask, proven = dcp_exact.solve_exact(p, t0 + LARGE_DEADLINE_S, incumbent=best)
            proven = keep(mask) and bool(proven)
            method = "search+exact"
        except Exception:  # noqa: BLE001
            proven = False
            _report("solve_exact")
    return best, method, proven, in_profile


def run(raw: bytes, t0: float) -> dict:
    """Return the response object for the raw request bytes. Never raises."""
    LAST_DIAG.update(method="none", active=0, proven=False)
    try:
        req = dcp_validate.validate_request(raw)
    except dcp_validate.InvalidRequest as exc:
        LAST_DIAG["method"] = "invalid"
        return {"status": "invalid", "reason": _reason(exc, "invalid request")}
    except BaseException:  # noqa: BLE001
        _report("validation")
        LAST_DIAG["method"] = "error"
        return {"status": "invalid", "reason": "internal error"}

    try:
        p = dcp_model.build_problem(req)
    except dcp_model.Infeasible as exc:
        LAST_DIAG["method"] = "infeasible"
        return {"status": "infeasible", "reason": _reason(exc, "mandatory cards cannot form a legal set")}
    except BaseException:  # noqa: BLE001
        _report("model construction")
        LAST_DIAG["method"] = "error"
        return {"status": "invalid", "reason": "internal error: model construction failed"}

    LAST_DIAG["active"] = p.n
    mask = p.mandatory
    in_profile = False
    try:
        mask, method, proven, in_profile = _solve(req, p, t0)
        LAST_DIAG.update(method=method, proven=proven)
    except BaseException:  # noqa: BLE001
        _report("solver dispatch")
        LAST_DIAG["method"] = "mandatory"
    try:
        legal = dcp_model.is_legal(p, mask)
    except BaseException:  # noqa: BLE001
        legal = False
    if not legal:
        mask = p.mandatory
        LAST_DIAG.update(method="mandatory", proven=False)

    fmask = dcp_model.mask_cover(p, mask)
    resp = {
        "status": "ok",
        "selected": dcp_model.mask_ids(p, mask),
        "tokens": dcp_model.mask_tokens(p, mask),
        "covered": dcp_model.fmask_ids(p, fmask),
        "utility": dcp_model.cover_weight(p, fmask),
    }
    if in_profile:
        try:
            certificate = dcp_profile.build_certificate(p, mask)
            if certificate is not None:
                resp["certificate"] = certificate
        except BaseException:  # noqa: BLE001
            _report("build_certificate")
    return resp


def _reason(exc: BaseException, default: str) -> str:
    """A nonempty printable-ASCII reason of bounded length."""
    try:
        text = "".join(ch if " " <= ch <= "~" else "?" for ch in str(exc))[:200].strip()
    except Exception:  # noqa: BLE001
        text = ""
    return text or default


def elapsed_ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)
