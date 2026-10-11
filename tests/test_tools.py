"""Tests for the packaging and post-run tools in ``tools/`` (no Docker, no network)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RESOURCES = REPO / "resources"
STUB = 'import sys\nsys.stdin.read()\nprint(\'{"status":"invalid","reason":"stub"}\')\n'


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"dcp_tool_{name}", REPO / "tools" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_package = _load("build_package")
make_zip = _load("make_zip")
check_results = _load("check_results")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_source(root: Path) -> Path:
    """A throwaway source tree with copies of the supplied files and some files that must not ship."""
    source = root / "src"
    (source / "resources").mkdir(parents=True)
    for name in build_package.RESOURCE_COPIES:
        shutil.copyfile(RESOURCES / name, source / "resources" / name)
    (source / "resources" / "task.md").write_text("not shipped\n")
    (source / "context_solver.py").write_text(STUB)
    (source / "dcp_model.py").write_text("X = 1\n")
    (source / "README.md").write_text("# readme\n")
    (source / "CLAUDE.md").write_text("no\n")
    (source / ".gitignore").write_text("no\n")
    (source / "gate.log").write_text("no\n")
    (source / ".DS_Store").write_text("no\n")
    for rel in ("tests/test_a.py", "tests/data/case.json", "tools/t.py", "tests/__pycache__/a.cpython-311.pyc",
                "tests/.DS_Store", "tests/gate.log", "tools/old.pyc", "docs/note.md", "build/pkg/x.py",
                ".claude/settings.json", ".claude-hve-tracking/plans/p.md", "__pycache__/c.pyc"):
        path = source / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x = 1\n")
    return source


class BuildPackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.source = _make_source(self.root)
        self.out = self.root / "out"

    def _packaged(self) -> set[str]:
        return {p.relative_to(self.out).as_posix() for p in self.out.rglob("*") if p.is_file()}

    def test_baseline_matches_repo_resources(self) -> None:
        for name, expected in build_package.RESOURCE_BASELINE.items():
            self.assertEqual(_sha(RESOURCES / name), expected, name)
        self.assertEqual(check_results.RUNNER_SHA256, build_package.RESOURCE_BASELINE["benchmark_runner.py"])
        self.assertEqual(check_results.INPUTS_SHA256, build_package.RESOURCE_BASELINE["benchmark_inputs.json"])

    def test_package_contents_and_byte_identical_supplied_files(self) -> None:
        self.assertEqual(build_package.main(["--source", str(self.source), "--out", str(self.out)]), 0)
        self.assertEqual(self._packaged(), {
            "context_solver.py", "dcp_model.py", "README.md", "tests/test_a.py", "tests/data/case.json",
            "tools/t.py", "benchmark_runner.py", "benchmark_inputs.json", "director_session.json"})
        for name in build_package.RESOURCE_COPIES:
            self.assertEqual((self.out / name).read_bytes(), (RESOURCES / name).read_bytes(), name)

    def test_recorder_output_is_copied_when_present(self) -> None:
        (self.source / "benchmark_results.json").write_text("{}\n")
        (self.source / "benchmark_run.log").write_text("line\n")
        build_package.build(self.source, self.out)
        self.assertLessEqual({"benchmark_results.json", "benchmark_run.log"}, self._packaged())

    def test_refuses_on_resource_hash_mismatch(self) -> None:
        for name in build_package.RESOURCE_BASELINE:
            with self.subTest(name=name):
                source = _make_source(self.root / name)
                with (source / "resources" / name).open("ab") as handle:
                    handle.write(b"\n")
                out = self.root / name / "out"
                self.assertEqual(build_package.main(["--source", str(source), "--out", str(out)]), 1)
                self.assertFalse(out.exists())

    def test_refuses_missing_entrypoint_and_nonempty_out(self) -> None:
        self.out.mkdir()
        (self.out / "leftover").write_text("x")
        with self.assertRaises(build_package.PackageError):
            build_package.build(self.source, self.out)
        (self.source / "context_solver.py").unlink()
        with self.assertRaises(build_package.PackageError):
            build_package.build(self.source, self.root / "out2")

    def _write_results(self, sources: dict) -> None:
        (self.source / "benchmark_results.json").write_text(json.dumps({"python_sources_after": sources}))

    def _recorded_sources(self) -> dict:
        names = ["context_solver.py", "dcp_model.py", "tests/test_a.py", "tools/t.py"]
        sources = {name: _sha(self.source / name) for name in names}
        sources["benchmark_runner.py"] = build_package.RESOURCE_BASELINE["benchmark_runner.py"]
        return sources

    def test_verify_results_accepts_matching_sources(self) -> None:
        self._write_results(self._recorded_sources())
        args = ["--source", str(self.source), "--out", str(self.out), "--verify-results"]
        self.assertEqual(build_package.main(args), 0)

    def test_verify_results_rejects_changed_missing_and_extra_sources(self) -> None:
        good = self._recorded_sources()
        changed = dict(good, **{"dcp_model.py": "0" * 64})
        missing = {k: v for k, v in good.items() if k != "tools/t.py"}
        extra = dict(good, **{"dcp_gone.py": "0" * 64})
        for label, sources in (("changed", changed), ("missing", missing), ("extra", extra)):
            with self.subTest(label=label):
                self._write_results(sources)
                out = self.root / f"out_{label}"
                args = ["--source", str(self.source), "--out", str(out), "--verify-results"]
                self.assertEqual(build_package.main(args), 1)

    def test_without_flag_results_are_not_verified(self) -> None:
        self._write_results({})
        self.assertEqual(build_package.main(["--source", str(self.source), "--out", str(self.out)]), 0)


class MakeZipTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.pkg = self.root / "pkg"
        for rel in ("context_solver.py", "tests/test_a.py", "tests/data/case.json", "tools/run.sh",
                    "__pycache__/a.pyc", "tests/__pycache__/b.pyc", ".DS_Store", "tests/.DS_Store"):
            path = self.pkg / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"{rel}\n")
        (self.pkg / "tools" / "run.sh").chmod(0o755)

    def test_files_at_archive_root_sorted_without_excluded_names(self) -> None:
        target = self.root / "a.zip"
        self.assertEqual(make_zip.main([str(self.pkg), str(target)]), 0)
        with zipfile.ZipFile(target) as archive:
            names = archive.namelist()
            infos = archive.infolist()
            self.assertEqual(archive.read("tests/test_a.py"), b"tests/test_a.py\n")
        self.assertEqual(names, ["context_solver.py", "tests/data/case.json", "tests/test_a.py", "tools/run.sh"])
        for info in infos:
            self.assertEqual(info.date_time, make_zip.FIXED_TIME)
            self.assertEqual(info.compress_type, zipfile.ZIP_DEFLATED)
        modes = {info.filename: (info.external_attr >> 16) & 0o777 for info in infos}
        self.assertEqual(modes["tools/run.sh"], 0o755)
        self.assertEqual(modes["context_solver.py"], 0o644)

    def test_archive_bytes_are_deterministic(self) -> None:
        first, second = self.root / "a.zip", self.root / "b.zip"
        make_zip.make_zip(self.pkg, first)
        (self.pkg / "context_solver.py").touch()
        make_zip.make_zip(self.pkg, second)
        self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_zip_inside_the_directory_does_not_contain_itself(self) -> None:
        target = self.pkg / "out.zip"
        make_zip.make_zip(self.pkg, target)
        with zipfile.ZipFile(target) as archive:
            self.assertNotIn("out.zip", archive.namelist())


class CheckResultsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.checker = check_results.load_checker()
        full = json.loads((RESOURCES / "benchmark_inputs.json").read_text(encoding="utf-8"))
        by_id = {item["id"]: item for item in full["instances"]}
        cls.invalid_id = "i_93a288225d57a93686"
        cls.infeasible_id = "i_6bf2ce5fc66d4bad9e"
        cls.corpus = {"schema": full["schema"], "instances": [by_id[cls.invalid_id], by_id[cls.infeasible_id]]}

    def _record(self, rid: str, response: dict, **overrides) -> dict:
        request = next(i["request"] for i in self.corpus["instances"] if i["id"] == rid)
        record = {"stdout": json.dumps(response) + "\n", "stderr": "", "exit_code": 0, "wall_ms": 40.2,
                  "peak_rss_kib": 9000, "timed_out": False, "id": rid,
                  "input_sha256": check_results.canonical_sha256(request), "response": response,
                  "response_parse_error": None}
        record.update(overrides)
        return record

    def _results(self, records: list, **overrides) -> dict:
        results = {"runner_sha256": check_results.RUNNER_SHA256, "inputs_sha256": check_results.INPUTS_SHA256,
                   "python_sources_unchanged": True,
                   "environment": {"cpu_capacity": {"quota_vcpus": 2.0}}, "instances": records}
        results.update(overrides)
        return results

    def _good_records(self) -> list:
        return [self._record(self.invalid_id, {"status": "invalid", "reason": "bad"}),
                self._record(self.infeasible_id, {"status": "infeasible", "reason": "no"})]

    def _evaluate(self, results: dict) -> dict:
        return check_results.evaluate(results, self.corpus, self.checker, expected_records=2)

    def test_correct_run_passes(self) -> None:
        summary = self._evaluate(self._results(self._good_records()))
        self.assertTrue(summary["passed"], summary["failed_ids"])
        self.assertEqual(summary["status_counts"], {"invalid": 1, "infeasible": 1})
        self.assertEqual([r["verdict"] for r in summary["rows"]], ["pass", "pass"])
        self.assertIn("RESULT: PASS", check_results.render(summary))

    def test_wrong_status_fails(self) -> None:
        records = [self._record(self.invalid_id, {"status": "infeasible", "reason": "x"}),
                   self._record(self.infeasible_id, {"status": "invalid", "reason": "stub"})]
        summary = self._evaluate(self._results(records))
        self.assertFalse(summary["passed"])
        self.assertEqual(summary["failed_ids"], [self.invalid_id, self.infeasible_id])
        self.assertIn("| FAIL |", check_results.render(summary))

    def test_integrity_fields_fail(self) -> None:
        cases = {"runner_sha256": "0" * 64, "inputs_sha256": "0" * 64, "python_sources_unchanged": False,
                 "environment": {"cpu_capacity": {"quota_vcpus": None}}}
        for key, value in cases.items():
            with self.subTest(key=key):
                summary = self._evaluate(self._results(self._good_records(), **{key: value}))
                self.assertFalse(summary["passed"])
                self.assertEqual(summary["failed_ids"], [])
        summary = check_results.evaluate(self._results(self._good_records()), self.corpus, self.checker)
        self.assertFalse(summary["passed"], "2 records is not 28")

    def test_record_limits_fail(self) -> None:
        cases = {"exit_code": 1, "timed_out": True, "response_parse_error": "x", "wall_ms": 5000.0,
                 "peak_rss_kib": 262144, "input_sha256": "0" * 64, "stdout": '{"status":"invalid","reason":"bad"}'}
        for key, value in cases.items():
            with self.subTest(key=key):
                records = self._good_records()
                records[0][key] = value
                summary = self._evaluate(self._results(records))
                self.assertEqual(summary["failed_ids"], [self.invalid_id])

    def test_stdout_shape(self) -> None:
        self.assertTrue(check_results.stdout_is_one_object('{"a": 1}\n'))
        for bad in ('{"a": 1}', '{"a": 1}\n\n', ' {"a": 1}\n', '{"a": 1}\n{"b": 2}\n', "[1]\n", "\n", "", None):
            with self.subTest(bad=bad):
                self.assertFalse(check_results.stdout_is_one_object(bad))

    def test_nearest_rank_p95(self) -> None:
        self.assertIsNone(check_results.nearest_rank_p95([]))
        self.assertEqual(check_results.nearest_rank_p95([7.0]), 7.0)
        self.assertEqual(check_results.nearest_rank_p95([float(v) for v in range(20, 0, -1)]), 19.0)
        self.assertEqual(check_results.nearest_rank_p95([float(v) for v in range(1, 22)]), 20.0)

    def test_main_exit_codes_and_json_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            shutil.copyfile(RESOURCES / "benchmark_inputs.json", run_dir / "benchmark_inputs.json")
            results = self._results(self._good_records())
            (run_dir / "benchmark_results.json").write_text(json.dumps(results), encoding="utf-8")
            out = run_dir / "summary.json"
            import contextlib
            import io
            with contextlib.redirect_stdout(io.StringIO()) as text, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(check_results.main([str(run_dir), "--json", str(out)]), 1)
                self.assertEqual(check_results.main([str(run_dir), "--allow-wrong"]), 0)
                self.assertEqual(check_results.main([str(run_dir / "missing")]), 1)
            self.assertIn("RESULT: FAIL", text.getvalue())
            self.assertFalse(json.loads(out.read_text(encoding="utf-8"))["passed"])


if __name__ == "__main__":
    unittest.main()
