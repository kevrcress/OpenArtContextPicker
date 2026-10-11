"""Dispatch for one director context request: validate, build the model, pick a solver, answer.

``run`` never raises. Deadlines are ``time.perf_counter()`` values measured from ``t0``, the
moment the process started. After the model exists every failure path still answers ``ok`` with
a legal set: the best legal mask found so far, and at least the mandatory closure.

Solver deadlines are cooperative. Where the platform has ``signal.setitimer``, a real-time
alarm at ``HARD_DEADLINE_S`` after process start interrupts a stage that ignores its deadline.
"""

from __future__ import annotations

import signal
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
HARD_DEADLINE_S = 4.0  # seconds after process start; enforced by a real-time alarm, not by the solvers

# Facts about the last call of ``run``, for the one-line stderr diagnostic of the CLI.
LAST_DIAG = {"method": "none", "active": 0, "proven": False}


class _HardDeadline(BaseException):
    """Raised by the watchdog alarm. Not an ``Exception``, so no solver stage swallows it."""


def _on_alarm(signum, frame) -> None:
    raise _HardDeadline()


def _arm_watchdog(t0: float) -> bool:
    """Arm a one-shot real-time alarm at ``t0 + HARD_DEADLINE_S``. False where that is impossible."""
    if not (hasattr(signal, "setitimer") and hasattr(signal, "SIGALRM")):
        return False
    try:
        signal.signal(signal.SIGALRM, _on_alarm)
    except ValueError:  # signal handlers can be set in the main thread only
        return False
    signal.setitimer(signal.ITIMER_REAL, max(t0 + HARD_DEADLINE_S - time.perf_counter(), 0.001))
    return True


def _disarm_watchdog() -> None:
    try:
        if hasattr(signal, "setitimer") and hasattr(signal, "ITIMER_REAL"):
            signal.setitimer(signal.ITIMER_REAL, 0)
    except Exception:  # noqa: BLE001
        pass


def _utility(p, mask: int) -> int:
    return dcp_model.cover_weight(p, dcp_model.mask_cover(p, mask))


def _report(stage: str) -> None:
    """Write the current exception to stderr; diagnostics must never break the answer."""
    try:
        sys.stderr.write(f"dcp_pipeline: {stage} failed\n{traceback.format_exc()}")
    except Exception:  # noqa: BLE001
        pass


def _solve(req: dict, p, t0: float, state: dict) -> tuple:
    """Return ``(mask, method, proven, in_profile)``; ``mask`` is legal, at least ``p.mandatory``.

    ``state["mask"]`` always holds the best legal mask so far, for a caller that is interrupted.
    """
    best = p.mandatory
    method = "mandatory"
    proven = False
    in_profile = False

    def keep(mask) -> bool:
        nonlocal best
        if type(mask) is int and dcp_model.is_legal(p, mask) and _utility(p, mask) >= _utility(p, best):
            best = mask
            state["mask"] = mask
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


def _stages(raw: bytes, t0: float, state: dict):
    """Validate, build the model and solve. Return a non-ok response, or None with ``state`` filled."""
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

    state["mask"] = p.mandatory
    state["p"] = p  # from here on the answer is ok
    LAST_DIAG.update(active=p.n, method="mandatory")
    mask, method, proven, state["in_profile"] = _solve(req, p, t0, state)
    state["mask"] = mask
    LAST_DIAG.update(method=method, proven=proven)
    return None


def _response(p, mask: int, in_profile: bool) -> dict:
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


def _floor_response(p) -> dict:
    """The ok response for the mandatory closure, built without any helper call."""
    mandatory = p.mandatory
    selected = []
    tokens = 0
    fmask = 0
    for i in range(len(p.ids)):
        if mandatory >> i & 1:
            selected.append(p.ids[i])
            tokens += p.tokens[i]
            fmask |= p.cover[i]
    covered = []
    utility = 0
    for k in range(len(p.feat_ids)):
        if fmask >> k & 1:
            covered.append(p.feat_ids[k])
            utility += p.feat_w[k]
    return {"status": "ok", "selected": selected, "tokens": tokens, "covered": covered, "utility": utility}


def run(raw: bytes, t0: float) -> dict:
    """Return the response object for the raw request bytes. Never raises."""
    LAST_DIAG.update(method="none", active=0, proven=False)
    state = {}
    early = None
    try:
        try:
            _arm_watchdog(t0)
            early = _stages(raw, t0, state)
        finally:
            _disarm_watchdog()
    except _HardDeadline:
        _report("hard deadline reached; pipeline")
        LAST_DIAG.update(method="watchdog", proven=False)
    except BaseException:  # noqa: BLE001
        _report("solver dispatch")
        LAST_DIAG.update(method="mandatory", proven=False)

    p = state.get("p")
    if p is None:  # validation or model construction did not finish
        if early is not None:
            return early
        LAST_DIAG["method"] = "error"
        return {"status": "invalid", "reason": "internal error"}

    # The model exists: every path below answers ok with a legal set.
    try:
        mask = state["mask"]
        legal = type(mask) is int and dcp_model.is_legal(p, mask)
    except BaseException:  # noqa: BLE001
        legal = False
    if not legal:
        mask = p.mandatory
        LAST_DIAG.update(method="mandatory", proven=False)
    for attempt in (mask, p.mandatory):
        try:
            return _response(p, attempt, bool(state.get("in_profile")))
        except BaseException:  # noqa: BLE001
            _report("response construction")
            LAST_DIAG.update(method="mandatory", proven=False)
    try:
        return _floor_response(p)
    except BaseException:  # noqa: BLE001 - last resort; nothing legal could be written down
        _report("floor response")
        LAST_DIAG["method"] = "error"
        return {"status": "invalid", "reason": "internal error"}


def _reason(exc: BaseException, default: str) -> str:
    """A nonempty printable-ASCII reason of bounded length."""
    try:
        text = "".join(ch if " " <= ch <= "~" else "?" for ch in str(exc))[:200].strip()
    except Exception:  # noqa: BLE001
        text = ""
    return text or default


def elapsed_ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)
