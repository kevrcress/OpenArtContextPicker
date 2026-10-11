"""The CLI contract of ``context_solver.py`` and the fallback paths of ``dcp_pipeline.run``."""

import contextlib
import io
import json
import os
import random
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import checker
import gen

import dcp_exact
import dcp_model
import dcp_pipeline
import dcp_search
import dcp_validate

ROOT = Path(__file__).resolve().parent.parent
SOLVER = ROOT / "context_solver.py"
OK_KEYS = {"status", "selected", "tokens", "covered", "utility"}


WALL_LIMIT_S = 5.0  # the contract's wall time per invocation, startup included
HAS_WATCHDOG = hasattr(signal, "setitimer") and hasattr(signal, "SIGALRM")
NO_WATCHDOG = "signal.setitimer is unavailable on this platform, so the pipeline has no hard time guard to test"


def run_cli(raw: bytes, *, cwd=None, argv=None, stdout=subprocess.PIPE) -> tuple:
    """Run the solver as a subprocess; return ``(completed process, wall seconds)``.

    Every CLI case goes through here, so every case asserts the contract's wall-time limit.
    """
    start = time.perf_counter()
    proc = subprocess.run(argv or [sys.executable, str(SOLVER)], input=raw, stdout=stdout, stderr=subprocess.PIPE,
                          cwd=cwd, timeout=10)
    wall = time.perf_counter() - start
    if wall >= WALL_LIMIT_S:
        raise AssertionError(f"the CLI took {wall:.3f} s; the limit is {WALL_LIMIT_S} s")
    return proc, wall


def one_object(test: unittest.TestCase, proc) -> dict:
    """Assert exit code 0 and exactly one JSON object followed by one newline on stdout."""
    test.assertEqual(proc.returncode, 0, proc.stderr[-2000:])
    out = proc.stdout.decode("ascii")
    test.assertTrue(out.endswith("\n"), out[-200:])
    test.assertEqual(out.count("\n"), 1, out[:500])
    resp = json.loads(out)
    test.assertIsInstance(resp, dict)
    return resp


class _Done:
    """The three fields of a finished process that ``one_object`` reads."""

    def __init__(self, returncode, stdout, stderr):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


def encode(request: dict) -> bytes:
    return json.dumps(request).encode("utf-8")


def session_bytes() -> bytes:
    for path in (ROOT / "director_session.json", ROOT / "resources" / "director_session.json"):
        if path.is_file():
            return path.read_bytes()
    raise AssertionError("director_session.json not found at the root or under resources/")


def infeasible_request() -> dict:
    """Two mandatory cards that contradict each other."""
    request = gen.random_request(random.Random(11), 3, p_requires=0.0, p_group=0.0, n_pairs=0)
    first, second = sorted(c["id"] for c in request["cards"])[:2]
    request["mandatory"] = [first, second]
    request["contradictions"] = [[first, second]]
    request["budget"] = 8192
    return request


def quiet_run(raw: bytes) -> dict:
    """``dcp_pipeline.run`` with its stderr diagnostics captured."""
    with contextlib.redirect_stderr(io.StringIO()):
        return dcp_pipeline.run(raw, time.perf_counter())


class CliContractTest(unittest.TestCase):
    def test_ok_response_is_one_line_with_exact_keys(self):
        raw = session_bytes()
        proc, _ = run_cli(raw)
        resp = one_object(self, proc)
        self.assertEqual(set(resp), OK_KEYS)
        self.assertEqual(resp["status"], "ok")
        self.assertEqual(resp["utility"], 61)
        self.assertEqual(checker.check_response(json.loads(raw), resp), [])
        self.assertIn(b"method=exact", proc.stderr)
        self.assertIn(b"proven=True", proc.stderr)

    def test_runs_from_a_different_working_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc, _ = run_cli(session_bytes(), cwd=tmp)
            self.assertEqual(one_object(self, proc)["utility"], 61)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_invalid_request(self):
        request = json.loads(session_bytes())
        request["budget"] = -1
        proc, _ = run_cli(encode(request))
        resp = one_object(self, proc)
        self.assertEqual(checker.check_response(request, resp, request_valid=False), [])

    def test_infeasible_request(self):
        request = infeasible_request()
        self.assertFalse(checker.expected_feasible(request))
        proc, _ = run_cli(encode(request))
        resp = one_object(self, proc)
        self.assertEqual(resp["status"], "infeasible")
        self.assertEqual(checker.check_response(request, resp), [])

    def test_empty_garbage_and_oversize_input_answer_invalid(self):
        cases = {
            "empty": b"",
            "garbage": b"\xff\xfe\x00not json at all\n\n{",
            "newlines": b"\n\n\n",
            "two objects": b"{}\n{}\n",
            "oversize": b" " * (dcp_validate.MAX_BYTES + 5),
        }
        for name, raw in cases.items():
            with self.subTest(name):
                proc, _ = run_cli(raw)
                resp = one_object(self, proc)
                self.assertEqual(set(resp), {"status", "reason"})
                self.assertEqual(resp["status"], "invalid")
                self.assertTrue(resp["reason"])

    def test_oversize_writer_that_keeps_stdin_open_gets_invalid(self):
        proc = subprocess.Popen([sys.executable, str(SOLVER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        start = time.perf_counter()

        def feed():
            try:
                proc.stdin.write(b" " * (dcp_validate.MAX_BYTES + 1))
                proc.stdin.flush()
            except OSError:
                pass

        writer = threading.Thread(target=feed, daemon=True)
        writer.start()
        try:
            try:
                proc.wait(timeout=10)  # stdin is still open here: the answer must not wait for EOF
            except subprocess.TimeoutExpired:
                self.fail("no response while the writer keeps stdin open")
            wall = time.perf_counter() - start
            out = proc.stdout.read()
            proc.stdout.close()
            resp = one_object(self, _Done(proc.returncode, out, proc.stderr.read()))
            self.assertEqual(set(resp), {"status", "reason"})
            self.assertEqual(resp["status"], "invalid")
            self.assertLess(wall, WALL_LIMIT_S)
        finally:
            proc.kill()
            writer.join(timeout=10)
            for stream in (proc.stdin, proc.stderr):
                try:
                    stream.close()
                except OSError:
                    pass
            proc.wait()

    def test_closed_stdout_exits_non_zero(self):
        read_end, write_end = os.pipe()
        os.close(read_end)  # nobody will ever read: the child's write fails with a broken pipe
        try:
            proc, _ = run_cli(session_bytes(), stdout=write_end)
        finally:
            os.close(write_end)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn(b"could not write the response to stdout", proc.stderr)

    def test_missing_stdout_exits_non_zero(self):
        code = (
            "import sys\n"
            f"sys.path.insert(0, {str(ROOT)!r})\n"
            "sys.stdout = None\n"
            "import context_solver\n"
            "sys.exit(context_solver.main())\n"
        )
        proc, _ = run_cli(session_bytes(), argv=[sys.executable, "-c", code])
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, b"")

    def _inject(self, prelude: str) -> dict:
        code = (
            "import sys\n"
            f"sys.path.insert(0, {str(ROOT)!r})\n"
            f"{prelude}\n"
            "import context_solver\n"
            "sys.exit(context_solver.main())\n"
        )
        proc, _ = run_cli(session_bytes(), argv=[sys.executable, "-c", code])
        return one_object(self, proc)

    def test_crash_in_validation_still_answers_one_line(self):
        resp = self._inject(
            "import dcp_validate\n"
            "def boom(raw):\n"
            "    raise RuntimeError('injected')\n"
            "dcp_validate.validate_request = boom"
        )
        self.assertEqual(resp, {"status": "invalid", "reason": "internal error"})

    def test_crash_before_the_pipeline_loads_still_answers_one_line(self):
        resp = self._inject("sys.modules['dcp_pipeline'] = None")
        self.assertEqual(resp, {"status": "invalid", "reason": "internal error"})

    def test_keyboard_interrupt_in_a_solver_still_answers_ok(self):
        resp = self._inject(
            "import dcp_exact\n"
            "def boom(*a, **k):\n"
            "    raise KeyboardInterrupt\n"
            "dcp_exact.solve_exact = boom"
        )
        self.assertEqual(resp["status"], "ok")
        self.assertEqual(checker.check_response(json.loads(session_bytes()), resp), [])


class FallbackTest(unittest.TestCase):
    """A solver that raises or returns an illegal mask leaves the mandatory closure as the answer."""

    def _request(self, n_cards: int) -> dict:
        for seed in range(100):
            request = gen.random_request(random.Random(seed), n_cards, n_mandatory=2, budget_ratio=0.6)
            if checker.expected_feasible(request) and len(checker.active_cards(request)) == n_cards:
                return request
        raise AssertionError("no feasible request generated")

    def _assert_mandatory_closure(self, request: dict, resp: dict) -> None:
        self.assertEqual(resp["status"], "ok")
        self.assertEqual(set(resp), OK_KEYS)
        self.assertEqual(checker.check_response(request, resp), [])
        self.assertEqual(resp["selected"], sorted(checker.requires_closure(request, request["mandatory"])))

    def test_solve_large_raising_gives_mandatory_closure(self):
        request = self._request(120)
        self.assertGreater(quiet_run(encode(request))["utility"], 0)
        with mock.patch.object(dcp_search, "solve_large", side_effect=RuntimeError("injected")):
            resp = quiet_run(encode(request))
        self._assert_mandatory_closure(request, resp)

    def test_solve_large_returning_an_illegal_mask_gives_mandatory_closure(self):
        request = self._request(120)
        for bad in (-1, (1 << 120) - 1, None, "x"):
            with self.subTest(bad=bad), mock.patch.object(dcp_search, "solve_large", return_value=bad):
                self._assert_mandatory_closure(request, quiet_run(encode(request)))

    def test_solve_exact_raising_gives_mandatory_closure(self):
        request = self._request(12)
        with mock.patch.object(dcp_exact, "solve_exact", side_effect=RecursionError("injected")):
            resp = quiet_run(encode(request))
        self._assert_mandatory_closure(request, resp)

    def test_mid_range_keeps_the_search_result_when_exact_raises(self):
        request = self._request(40)
        problem = dcp_model.build_problem(dcp_validate.validate_request(encode(request)))
        expected = dcp_search.solve_large(problem, time.perf_counter() + 0.2)
        with mock.patch.object(dcp_search, "solve_large", return_value=expected), \
                mock.patch.object(dcp_exact, "solve_exact", side_effect=MemoryError("injected")):
            resp = quiet_run(encode(request))
        self.assertEqual(checker.check_response(request, resp), [])
        self.assertEqual(resp["selected"], dcp_model.mask_ids(problem, expected))

    def test_mid_range_with_both_solvers_raising_gives_mandatory_closure(self):
        request = self._request(40)
        with mock.patch.object(dcp_search, "solve_large", side_effect=ValueError("injected")), \
                mock.patch.object(dcp_exact, "solve_exact", side_effect=ValueError("injected")):
            resp = quiet_run(encode(request))
        self._assert_mandatory_closure(request, resp)

    def test_profile_solver_raising_falls_through_to_the_next_method(self):
        request = gen.random_request(random.Random(4), 10, p_requires=0.0, p_group=0.0, n_pairs=0, max_covers=1)
        import dcp_profile
        import oracle

        with mock.patch.object(dcp_profile, "solve_profile", side_effect=RuntimeError("injected")):
            resp = quiet_run(encode(request))
        self.assertEqual(checker.check_response(request, resp), [])
        self.assertEqual(resp["utility"], oracle.best_utility(request))

    def test_model_construction_crash_answers_invalid(self):
        with mock.patch.object(dcp_model, "build_problem", side_effect=RuntimeError("injected")):
            resp = quiet_run(session_bytes())
        self.assertEqual(resp, {"status": "invalid", "reason": "internal error: model construction failed"})

    def test_run_never_raises_on_non_bytes(self):
        self.assertEqual(quiet_run(None)["status"], "invalid")


def _sleeper(*args, **kwargs):
    """A solver that ignores its deadline."""
    time.sleep(6)
    raise AssertionError("the watchdog did not interrupt the sleeping solver")


@unittest.skipUnless(HAS_WATCHDOG, NO_WATCHDOG)
class HardDeadlineTest(unittest.TestCase):
    """A solver that ignores its deadline is interrupted; the answer is the best legal set already held."""

    LIMIT_S = 4.6

    def _timed(self, request: dict) -> dict:
        start = time.perf_counter()
        resp = quiet_run(encode(request))
        wall = time.perf_counter() - start
        self.assertLess(wall, self.LIMIT_S)
        self.assertGreater(wall, 3.0, "the solver was not reached, so the watchdog was not exercised")
        self.assertEqual(resp["status"], "ok")
        self.assertEqual(checker.check_response(request, resp), [])
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL)[0], 0.0)
        return resp

    def _mandatory(self, request: dict) -> list:
        return sorted(checker.requires_closure(request, request["mandatory"]))

    def test_sleeping_exact_solver(self):
        request = json.loads(session_bytes())
        with mock.patch.object(dcp_exact, "solve_exact", side_effect=_sleeper):
            resp = self._timed(request)
        self.assertEqual(resp["selected"], self._mandatory(request))
        self.assertEqual(dcp_pipeline.LAST_DIAG["method"], "watchdog")

    def test_sleeping_large_solver(self):
        request = FallbackTest()._request(120)
        with mock.patch.object(dcp_search, "solve_large", side_effect=_sleeper):
            resp = self._timed(request)
        self.assertEqual(resp["selected"], self._mandatory(request))

    def test_sleeping_profile_solver(self):
        import dcp_profile

        request = gen.random_request(random.Random(4), 10, p_requires=0.0, p_group=0.0, n_pairs=0, max_covers=1)
        with mock.patch.object(dcp_profile, "solve_profile", side_effect=_sleeper):
            resp = self._timed(request)
        self.assertEqual(resp["selected"], self._mandatory(request))

    def test_sleeping_exact_solver_keeps_the_earlier_search_result(self):
        request = FallbackTest()._request(40)
        problem = dcp_model.build_problem(dcp_validate.validate_request(encode(request)))
        expected = dcp_search.solve_large(problem, time.perf_counter() + 0.2)
        with mock.patch.object(dcp_search, "solve_large", return_value=expected), \
                mock.patch.object(dcp_exact, "solve_exact", side_effect=_sleeper):
            resp = self._timed(request)
        self.assertEqual(resp["selected"], dcp_model.mask_ids(problem, expected))


class ResponseConstructionTest(unittest.TestCase):
    """Once the model exists, a failure while writing down the answer never changes ``ok`` to ``invalid``."""

    def test_mask_ids_failing_once_still_answers_ok(self):
        real = dcp_model.mask_ids
        calls = []

        def flaky(p, mask):
            calls.append(mask)
            if len(calls) == 1:
                raise MemoryError("injected")
            return real(p, mask)

        request = json.loads(session_bytes())
        with mock.patch.object(dcp_model, "mask_ids", side_effect=flaky):
            resp = quiet_run(session_bytes())
        self.assertGreaterEqual(len(calls), 2)
        self.assertEqual(resp["status"], "ok")
        self.assertEqual(set(resp), OK_KEYS)
        self.assertEqual(checker.check_response(request, resp), [])

    def test_every_helper_failing_still_answers_ok_with_the_mandatory_closure(self):
        request = FallbackTest()._request(12)
        boom = MemoryError("injected")
        with mock.patch.object(dcp_model, "mask_ids", side_effect=boom), \
                mock.patch.object(dcp_model, "fmask_ids", side_effect=boom), \
                mock.patch.object(dcp_model, "mask_tokens", side_effect=boom):
            resp = quiet_run(encode(request))
        self.assertEqual(resp["status"], "ok")
        self.assertEqual(set(resp), OK_KEYS)
        self.assertEqual(checker.check_response(request, resp), [])
        self.assertEqual(resp["selected"], sorted(checker.requires_closure(request, request["mandatory"])))


class ContractMaximumTest(unittest.TestCase):
    """Requests at the contract maxima through the CLI: legal and inside the time limit, startup included."""

    LIMIT_S = 4.0

    def _check(self, request: dict, label: str) -> None:
        proc, wall = run_cli(encode(request))
        resp = one_object(self, proc)
        self.assertEqual(resp["status"], "ok")
        self.assertEqual(checker.check_response(request, resp), [])
        sys.stderr.write(f"[contract maximum] {label}: wall {wall:.3f} s, utility {resp['utility']}, "
                         f"selected {len(resp['selected'])}\n")
        self.assertLess(wall, self.LIMIT_S)

    def test_coupled_maximum(self):
        request = gen.max_request(random.Random(8))
        self.assertEqual(len(checker.active_cards(request)), 500)
        self.assertEqual(len(request["contradictions"]), 10_000)
        self._check(request, "coupled")

    def test_profile_maximum(self):
        request = gen.max_request(random.Random(8), profile=True)
        self.assertTrue(checker.is_certificate_profile(request))
        self._check(request, "profile")


if __name__ == "__main__":
    unittest.main()
