"""Tests for the packaging and post-run tools in ``tools/`` (no Docker, no network)."""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def supplied(name: str) -> Path:
    """A supplied file: at the root in the extracted package, under ``resources/`` in the repository."""
    at_root = REPO / name
    return at_root if at_root.is_file() else REPO / "resources" / name


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
    """A throwaway repo-shaped source tree: the supplied files under ``resources/`` plus files that must not ship.

    Built from ``supplied`` so it is the same tree whether the tests run in the
    repository or in the extracted package (which has no ``resources/`` folder).
    """
    source = root / "src"
    (source / "resources").mkdir(parents=True)
    for name in build_package.RESOURCE_COPIES:
        shutil.copyfile(supplied(name), source / "resources" / name)
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
                ".claude/settings.json", "__pycache__/c.pyc"):
        path = source / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x = 1\n")
    return source


class BuildPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # The supplied corpus is large: locate and copy it out of the real tree once per class.
        cls._class_tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls._class_tmp.cleanup)
        cls.template = _make_source(Path(cls._class_tmp.name))
        cls.supplied_bytes = {name: (cls.template / "resources" / name).read_bytes()
                              for name in build_package.RESOURCE_COPIES}

    def _new_source(self, root: Path) -> Path:
        """A private, writable copy of the class's source tree at ``root/src``."""
        return Path(shutil.copytree(self.template, root / "src"))

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.source = self._new_source(self.root)
        self.out = self.root / "out"

    def _packaged(self) -> set[str]:
        return {p.relative_to(self.out).as_posix() for p in self.out.rglob("*") if p.is_file()}

    def test_baseline_matches_repo_resources(self) -> None:
        for name, expected in build_package.RESOURCE_BASELINE.items():
            self.assertEqual(_sha(supplied(name)), expected, name)
        self.assertEqual(check_results.RUNNER_SHA256, build_package.RESOURCE_BASELINE["benchmark_runner.py"])
        self.assertEqual(check_results.INPUTS_SHA256, build_package.RESOURCE_BASELINE["benchmark_inputs.json"])

    def test_package_contents_and_byte_identical_supplied_files(self) -> None:
        self.assertEqual(build_package.main(["--source", str(self.source), "--out", str(self.out)]), 0)
        self.assertEqual(self._packaged(), {
            "context_solver.py", "dcp_model.py", "README.md", "tests/test_a.py", "tests/data/case.json",
            "tools/t.py", "benchmark_runner.py", "benchmark_inputs.json", "director_session.json"})
        for name in build_package.RESOURCE_COPIES:
            self.assertEqual((self.out / name).read_bytes(), self.supplied_bytes[name], name)
            self.assertEqual(self.supplied_bytes[name], supplied(name).read_bytes(), name)

    def _add_tracking(self, *rels: str) -> None:
        for rel in rels:
            path = self.source / ".claude-hve-tracking" / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("x = 1\n")

    def _tracked(self) -> set[str]:
        prefix = ".claude-hve-tracking/"
        return {name[len(prefix):] for name in self._packaged() if name.startswith(prefix)}

    def test_durable_tracking_artifacts_are_copied(self) -> None:
        durable = {f"{name}/2026-10-11/a.md" for name in build_package.TRACKING_SUBDIRS}
        self.assertEqual(set(build_package.TRACKING_SUBDIRS), {
            "research", "plans", "details", "changes", "reviews", "challenges", "memory", "doc-ops"})
        self._add_tracking(*durable, "plans/logs/2026-10-11/a-log.md", "reviews/rpi/2026-10-11/r.md")
        files = build_package.build(self.source, self.out)
        self.assertEqual(self._tracked(), durable | {"plans/logs/2026-10-11/a-log.md", "reviews/rpi/2026-10-11/r.md"})
        self.assertLessEqual({".claude-hve-tracking/" + rel for rel in durable}, set(files))
        self.assertEqual((self.out / ".claude-hve-tracking/plans/2026-10-11/a.md").read_text(), "x = 1\n")

    def test_regenerable_and_private_tracking_content_is_not_copied(self) -> None:
        self._add_tracking(
            "plans/p.md", "research/subagents/2026-10-11/raw.md", "subagents/s.md", "sandbox/run-1/s.md",
            "gh-sync/state.json", "plans/gh-sync/state.json", "consults/c.md", "friction/f.md",
            "reviews/pr/branch/diff.patch", "reviews/pr/branch/review.md", "changes/other.patch",
            "changes/.DS_Store", "changes/__pycache__/x.md", "changes/gate.log", "top-level.md", "unknown/u.md")
        build_package.build(self.source, self.out)
        self.assertEqual(self._tracked(), {"plans/p.md", "reviews/pr/branch/review.md"})

    def test_python_under_the_tracking_folder_is_not_copied(self) -> None:
        self._add_tracking("plans/p.md", "plans/helper.py", "details/deep/tool.py", "changes/old.pyc")
        self._write_results(self._recorded_sources())  # the inventory of a tree with no tracking folder
        build_package.build(self.source, self.out, verify=True)
        self.assertEqual(self._tracked(), {"plans/p.md"})
        self.assertEqual([p for p in (self.out / ".claude-hve-tracking").rglob("*.py*")], [])

    def test_build_without_a_tracking_folder_succeeds(self) -> None:
        self.assertFalse((self.source / ".claude-hve-tracking").exists())
        self.assertEqual(build_package.main(["--source", str(self.source), "--out", str(self.out)]), 0)
        self.assertFalse((self.out / ".claude-hve-tracking").exists())

    def test_recorder_output_is_copied_when_present(self) -> None:
        (self.source / "benchmark_results.json").write_text("{}\n")
        (self.source / "benchmark_run.log").write_text("line\n")
        build_package.build(self.source, self.out)
        self.assertLessEqual({"benchmark_results.json", "benchmark_run.log"}, self._packaged())

    def test_refuses_on_resource_hash_mismatch(self) -> None:
        for name in build_package.RESOURCE_BASELINE:
            with self.subTest(name=name):
                source = self._new_source(self.root / name)
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
        (self.source / "benchmark_run.log").write_text("rc=0\n")

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
        cases = (("changed", changed, "changed since the recorded run: dcp_model.py"),
                 ("missing", missing, "not in the recorded run: tools/t.py"),
                 ("extra", extra, "recorded but not in the package: dcp_gone.py"))
        for label, sources, reason in cases:
            with self.subTest(label=label):
                self._write_results(sources)
                out = self.root / f"out_{label}"
                self.assertEqual(self._failed_final_build(self.source, out), 1)
                self.assertIn(reason, self._message)

    def _failed_final_build(self, source: Path, out: Path) -> int:
        """Run a final build expected to fail; keep its message and assert it left no output at all."""
        args = ["--source", str(source), "--out", str(out), "--verify-results"]
        with contextlib.redirect_stderr(io.StringIO()) as text, contextlib.redirect_stdout(io.StringIO()):
            code = build_package.main(args)  # an uncaught exception here is a traceback for the user
        self._message = text.getvalue()
        self.assertFalse(out.exists(), "a failed final build must not leave the output directory")
        leftovers = [p.name for p in out.parent.iterdir() if p.name.startswith(f".{out.name}.tmp-")]
        self.assertEqual(leftovers, [], "the temporary build directory is removed")
        self.assertIn("no output was written", self._message)
        return code

    def test_successful_build_leaves_no_temporary_directory(self) -> None:
        self._write_results(self._recorded_sources())
        for label, flags in (("staging", []), ("final", ["--verify-results"])):
            with self.subTest(label=label):
                out = self.root / f"ok_{label}"
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(build_package.main(["--source", str(self.source), "--out", str(out), *flags]), 0)
                self.assertTrue((out / "context_solver.py").is_file())
                self.assertEqual([p.name for p in self.root.iterdir() if ".tmp-" in p.name], [])

    def test_empty_existing_out_is_filled(self) -> None:
        self.out.mkdir()
        build_package.build(self.source, self.out)
        self.assertIn("context_solver.py", self._packaged())

    def test_without_flag_results_are_not_verified(self) -> None:
        self._write_results({})
        self.assertEqual(build_package.main(["--source", str(self.source), "--out", str(self.out)]), 0)

    def test_verify_results_requires_results_log_and_readme(self) -> None:
        self.assertEqual(set(build_package.REQUIRED_FINAL_FILES),
                         {"benchmark_results.json", "benchmark_run.log", "README.md"})
        for name in build_package.REQUIRED_FINAL_FILES:
            with self.subTest(missing=name):
                source = self._new_source(self.root / f"no_{name}")
                (source / "benchmark_results.json").write_text(
                    json.dumps({"python_sources_after": self._recorded_sources()}))
                (source / "benchmark_run.log").write_text("rc=0\n")
                (source / name).unlink()
                out = self.root / f"no_{name}" / "out"
                with self.assertRaisesRegex(build_package.PackageError, name.replace(".", r"\.")):
                    build_package.build(source, out, verify=True)
                self.assertFalse(out.exists(), "nothing is copied when a required file is missing")
                args = ["--source", str(source), "--out", str(out), "--verify-results"]
                with contextlib.redirect_stderr(io.StringIO()) as text:
                    self.assertEqual(build_package.main(args), 1)
                self.assertIn(name, text.getvalue())
                # verify_results itself refuses a package directory that lacks the file.
                build_package.build(source, out)
                with self.assertRaisesRegex(build_package.PackageError, name.replace(".", r"\.")):
                    build_package.verify_results(out)

    def test_without_flag_the_three_final_files_stay_optional(self) -> None:
        (self.source / "README.md").unlink()
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(build_package.main(["--source", str(self.source), "--out", str(self.out)]), 0)
        self.assertFalse({"README.md", "benchmark_results.json", "benchmark_run.log"} & self._packaged())

    def test_verify_results_rejects_unreadable_inventory(self) -> None:
        for label, text in (("no key", "{}"), ("not json", "{"), ("not an object", '{"python_sources_after": []}')):
            with self.subTest(label=label):
                source = self._new_source(self.root / label.replace(" ", "_"))
                (source / "benchmark_results.json").write_text(text)
                (source / "benchmark_run.log").write_text("rc=0\n")
                out = self.root / label.replace(" ", "_") / "out"
                with self.assertRaisesRegex(build_package.PackageError, "python_sources_after"):
                    build_package.build(source, out, verify=True)
                self.assertFalse(out.exists())
                self.assertEqual(self._failed_final_build(source, out), 1)
                self.assertIn("python_sources_after", self._message)

    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0, "root can read a mode-0 file")
    def test_verify_results_rejects_an_unreadable_results_file(self) -> None:
        self._write_results(self._recorded_sources())
        results = self.source / "benchmark_results.json"
        os.chmod(results, 0)
        self.addCleanup(os.chmod, results, 0o644)
        with self.assertRaises(PermissionError):
            results.read_bytes()
        self.assertEqual(self._failed_final_build(self.source, self.out), 1)
        self.assertIn("benchmark_results.json", self._message)
        self.assertIn("Permission denied", self._message)
        # The same failure met inside verify_results (file unreadable in the package itself).
        os.chmod(results, 0o644)
        build_package.build(self.source, self.out)
        os.chmod(self.out / "benchmark_results.json", 0)
        self.addCleanup(os.chmod, self.out / "benchmark_results.json", 0o644)
        with self.assertRaisesRegex(build_package.PackageError, "cannot read benchmark_results.json"):
            build_package.verify_results(self.out)


class RunRecordedScriptTests(unittest.TestCase):
    def test_docker_command_exits_with_the_recorder_status(self) -> None:
        text = (REPO / "tools" / "run_recorded.sh").read_text(encoding="utf-8")
        lines = [line for line in text.splitlines() if line.startswith("readonly RECORD_CMD=")]
        self.assertEqual(len(lines), 1)
        command = lines[0].split("=", 1)[1]
        self.assertTrue(command.startswith("'python benchmark_runner.py ") and command.endswith("'"), command)
        self.assertTrue(command.endswith('> benchmark_run.log 2>&1; rc=$?; echo "rc=$rc"; exit "$rc"\''), command)
        self.assertEqual(command.count(">"), 2, "only the recorder's own streams go to the log")
        # The outer script keeps the status past errexit and exits with it.
        self.assertIn('sh -c "${RECORD_CMD}" || rc=$?', text)
        self.assertIn('exit "${rc}"', text)
        self.assertIn("set -euo pipefail", text)

    FAKE_DOCKER = """#!/bin/sh
# Stands in for docker: "info" succeeds; "run" exits with FAKE_DOCKER_RC and, when
# that is 0, writes the results file into the directory mounted with -v.
if [ "$1" = "info" ]; then exit 0; fi
rc="${FAKE_DOCKER_RC:-7}"
prev=""
for arg in "$@"; do
  if [ "$prev" = "-v" ] && [ "$rc" = "0" ]; then echo '{}' > "${arg%:/work}/benchmark_results.json"; fi
  prev="$arg"
done
exit "$rc"
"""

    def _run_script(self, docker_rc: int, *, failing_find: bool = False, write_results: bool = True):
        """Execute run_recorded.sh with a fake ``docker`` (and optionally a failing ``find``) first on PATH."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        fake_bin, pkg = root / "bin", root / "pkg"
        fake_bin.mkdir()
        (pkg / "__pycache__").mkdir(parents=True)
        for name in ("context_solver.py", "benchmark_runner.py", "benchmark_inputs.json"):
            (pkg / name).write_text("x\n")
        fakes = {"docker": self.FAKE_DOCKER if write_results else "#!/bin/sh\n[ \"$1\" = info ] && exit 0\n"
                                                                 f"exit {docker_rc}\n"}
        if failing_find:
            fakes["find"] = "#!/bin/sh\necho 'fake find: cleanup failed' >&2\nexit 9\n"
        for name, body in fakes.items():
            (fake_bin / name).write_text(body)
            (fake_bin / name).chmod(0o755)
        env = dict(os.environ, PATH=f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
                   FAKE_DOCKER_RC=str(docker_rc))
        done = subprocess.run(["bash", str(REPO / "tools" / "run_recorded.sh"), str(pkg)], env=env,
                              capture_output=True, text=True, timeout=60)
        return done, pkg

    def test_script_exits_with_the_recorder_status(self) -> None:
        done, pkg = self._run_script(7)
        self.assertEqual(done.returncode, 7, done.stderr)
        self.assertIn("the recorder exited with status 7", done.stderr)
        self.assertFalse((pkg / "__pycache__").exists(), "the real cleanup ran")

    def test_failing_cleanup_does_not_mask_the_recorder_status(self) -> None:
        done, pkg = self._run_script(7, failing_find=True)
        self.assertIn("fake find: cleanup failed", done.stderr, "the cleanup step really failed")
        self.assertTrue((pkg / "__pycache__").exists())
        self.assertEqual(done.returncode, 7, done.stderr)
        self.assertIn("the recorder exited with status 7", done.stderr)

    def test_script_succeeds_when_the_recorder_does_even_if_cleanup_fails(self) -> None:
        for failing_find in (False, True):
            with self.subTest(failing_find=failing_find):
                done, pkg = self._run_script(0, failing_find=failing_find)
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertTrue((pkg / "benchmark_results.json").is_file())

    def test_script_fails_when_no_results_file_is_produced(self) -> None:
        done, _ = self._run_script(0, write_results=False)
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertIn("was not produced", done.stderr)


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

    def test_dot_directories_are_archived_and_gate_log_and_compiled_files_are_not(self) -> None:
        for rel in (".claude-hve-tracking/plans/2026-10-11/a-plan.md", "gate.log", "tests/gate.log",
                    ".claude-hve-tracking/changes/gate.log", "tools/old.pyc"):
            path = self.pkg / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"{rel}\n")
        target = self.root / "a.zip"
        self.assertEqual(make_zip.make_zip(self.pkg, target), 5)
        with zipfile.ZipFile(target) as archive:
            names = archive.namelist()
            self.assertEqual(archive.read(".claude-hve-tracking/plans/2026-10-11/a-plan.md"),
                             b".claude-hve-tracking/plans/2026-10-11/a-plan.md\n")
        self.assertEqual(names, [".claude-hve-tracking/plans/2026-10-11/a-plan.md", "context_solver.py",
                                 "tests/data/case.json", "tests/test_a.py", "tools/run.sh"])

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
        full = json.loads(supplied("benchmark_inputs.json").read_text(encoding="utf-8"))
        by_id = {item["id"]: item for item in full["instances"]}
        cls.invalid_id = "i_93a288225d57a93686"
        cls.infeasible_id = "i_6bf2ce5fc66d4bad9e"
        cls.corpus = {"schema": full["schema"], "instances": [by_id[cls.invalid_id], by_id[cls.infeasible_id]]}
        cls.by_id = by_id
        cls.feasible_id = "i_353b0868e8bfb0bb1c"  # valid, feasible, not a certificate profile
        cls.profile_id = "i_9e24f6f61fea4413ac"  # valid, feasible, certificate profile

    def _record(self, rid: str, response: dict, **overrides) -> dict:
        """One record with exactly the keys the recorder writes (meter output, id, hash, response)."""
        request = self.by_id[rid]["request"]
        record = {"stdout": json.dumps(response) + "\n", "stderr": "", "exit_code": 0, "wall_ms": 40.2,
                  "peak_rss_kib": 9000, "timed_out": False, "id": rid,
                  "input_sha256": check_results.canonical_sha256(request), "response": response,
                  "response_parse_error": None}
        record.update(overrides)
        return record

    def _sources(self) -> dict:
        return {"benchmark_runner.py": check_results.RUNNER_SHA256, "context_solver.py": "a" * 64,
                "dcp_model.py": "b" * 64, "tests/checker.py": "c" * 64}

    def _results(self, records: list, **overrides) -> dict:
        """The document shape ``resources/benchmark_runner.py`` writes, key for key."""
        results = {
            "schema": "openart-context-observations/2", "inputs_sha256": check_results.INPUTS_SHA256,
            "python_sources_before": self._sources(), "python_sources_after": self._sources(),
            "python_sources_unchanged": True, "runner_sha256": check_results.RUNNER_SHA256,
            "entrypoint_sha256": "a" * 64,
            "environment": {
                "python": "3.11.9 (main) [GCC 12.2.0]", "executable": "/usr/local/bin/python",
                "platform": "Linux-6.10-aarch64-with-glibc2.36", "logical_cpus": 8,
                "cpu_capacity": {"logical_cpus": 8, "affinity_cpus": [0, 1, 2, 3, 4, 5, 6, 7],
                                 "cgroup_cpu_max": "200000 100000", "quota_vcpus": 2.0},
                "rss_units": "KiB", "wall_limit_seconds": 5.0,
                "invocation": "benchmark_runner.py --solution context_solver.py --inputs benchmark_inputs.json"
                              " --output benchmark_results.json"},
            "instances": records}
        results.update(overrides)
        return results

    def _ok_response(self, rid: str) -> dict:
        request = self.by_id[rid]["request"]
        return self.checker.response_for(request, self.checker.requires_closure(request, request["mandatory"]))

    def _evaluate_one(self, rid: str, response: dict) -> dict:
        corpus = {"schema": self.corpus["schema"], "instances": [self.by_id[rid]]}
        return check_results.evaluate(self._results([self._record(rid, response)]), corpus, self.checker,
                                      expected_records=1)

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
        self.assertEqual([c["check"] for c in summary["integrity"] if not c["ok"]], [])

    def test_fixture_has_the_recorder_document_keys(self) -> None:
        results = self._results(self._good_records())
        self.assertEqual(list(results), ["schema", "inputs_sha256", "python_sources_before", "python_sources_after",
                                         "python_sources_unchanged", "runner_sha256", "entrypoint_sha256",
                                         "environment", "instances"])
        self.assertEqual(list(results["environment"]), ["python", "executable", "platform", "logical_cpus",
                                                        "cpu_capacity", "rss_units", "wall_limit_seconds",
                                                        "invocation"])
        self.assertEqual(set(results["instances"][0]), {"stdout", "stderr", "exit_code", "wall_ms", "peak_rss_kib",
                                                        "timed_out", "id", "input_sha256", "response",
                                                        "response_parse_error"})
        recorder = supplied("benchmark_runner.py").read_text(encoding="utf-8")
        for key in list(results) + list(results["environment"]) + list(results["instances"][0]):
            self.assertIn(f'"{key}"' if key not in ("id", "input_sha256") else f"{key}=", recorder, key)

    def test_stdout_and_stored_response_must_agree(self) -> None:
        good = {"status": "invalid", "reason": "bad"}
        wrong_stdout = json.dumps({"status": "infeasible", "reason": "bad"}) + "\n"
        cases = {
            "good response, wrong stdout": self._record(self.invalid_id, good, stdout=wrong_stdout),
            "wrong response, good stdout": dict(self._record(self.invalid_id, good),
                                                response={"status": "invalid", "reason": "other"}),
            "response dropped": dict(self._record(self.invalid_id, good), response=None),
            "non-finite constant": dict(self._record(self.invalid_id, good),
                                        stdout='{"status":"invalid","reason":NaN}\n',
                                        response={"status": "invalid", "reason": float("nan")}),
        }
        for label, record in cases.items():
            with self.subTest(label=label):
                summary = self._evaluate(self._results([record, self._good_records()[1]]))
                self.assertFalse(summary["passed"])
                self.assertEqual(summary["failed_ids"], [self.invalid_id])
        row = self._evaluate(self._results([cases["good response, wrong stdout"], self._good_records()[1]]))["rows"][0]
        self.assertEqual(row["status"], "infeasible", "the row reports what stdout said")
        self.assertIn("stored response differs from the object parsed from stdout", row["problems"])

    def test_parse_stdout_matches_the_recorder(self) -> None:
        self.assertEqual(check_results.parse_stdout('{"a": 1}\n'), ({"a": 1}, None))
        for bad in ('{"a": NaN}\n', '{"a": Infinity}\n', '{"a": -Infinity}\n', "{", "", None, b"{}"):
            with self.subTest(bad=bad):
                value, error = check_results.parse_stdout(bad)
                self.assertIsNone(value)
                self.assertTrue(error)
        self.assertTrue(check_results.same_json({"a": [1, "x"]}, {"a": [1, "x"]}))
        for first, second in ((1, 1.0), (1, True), ({"a": 1}, {"a": 2}), (None, {})):
            self.assertFalse(check_results.same_json(first, second))

    def test_schema_inventories_and_entrypoint_hash_are_required(self) -> None:
        def drop(key):
            return lambda r: r.pop(key)

        def put(key, value):
            return lambda r: r.__setitem__(key, value)

        def put_in(key, name, value):
            return lambda r: r[key].__setitem__(name, value)

        cases = {
            "missing schema": drop("schema"),
            "wrong schema": put("schema", "openart-context-observations/1"),
            "missing before inventory": drop("python_sources_before"),
            "missing after inventory": drop("python_sources_after"),
            "inventory is not an object": put("python_sources_after", ["context_solver.py"]),
            "file only in before": put_in("python_sources_before", "dcp_extra.py", "d" * 64),
            "file only in after": put_in("python_sources_after", "dcp_extra.py", "d" * 64),
            "hash changed during the run": put_in("python_sources_after", "dcp_model.py", "d" * 64),
            "unchanged flag missing": drop("python_sources_unchanged"),
            "unchanged flag is not a boolean": put("python_sources_unchanged", 1),
            "missing entry-point hash": drop("entrypoint_sha256"),
            "wrong entry-point hash": put("entrypoint_sha256", "e" * 64),
            "entry point not in the inventory": lambda r: [r[k].pop("context_solver.py") for k in
                                                           ("python_sources_before", "python_sources_after")],
            "recorder beside the solver differs": lambda r: [r[k].__setitem__("benchmark_runner.py", "f" * 64)
                                                             for k in ("python_sources_before", "python_sources_after")],
            "recorder missing from both inventories": lambda r: [r[k].pop("benchmark_runner.py") for k in
                                                                 ("python_sources_before", "python_sources_after")],
            "recorder missing from the before inventory": lambda r: r["python_sources_before"].pop(
                "benchmark_runner.py"),
        }
        for label, mutate in cases.items():
            with self.subTest(label=label):
                results = self._results(self._good_records())
                mutate(results)
                summary = self._evaluate(results)
                self.assertFalse(summary["passed"])
                self.assertEqual(summary["failed_ids"], [], "an integrity failure, not a record failure")
                self.assertIn("RESULT: FAIL", check_results.render(summary))
        results = self._results(self._good_records())
        for key in ("python_sources_before", "python_sources_after"):
            results[key].pop("benchmark_runner.py")
        summary = self._evaluate(results)
        self.assertFalse(summary["passed"], "an authentic observation always lists the recorder")
        failed = [c["check"] for c in summary["integrity"] if not c["ok"]]
        self.assertEqual(failed, ["benchmark_runner.py is in both source inventories",
                                  "python_sources_before/after[benchmark_runner.py] == runner_sha256"])
        self.assertNotIn("not applicable", check_results.render(summary))

    def _evaluate_pairs(self, mutate=None) -> dict:
        ids = [rid for pair in check_results.CONSISTENCY_PAIRS for rid in pair]
        responses = {rid: self._ok_response(rid) for rid in ids}
        if mutate is not None:
            mutate(responses)
        corpus = {"schema": self.corpus["schema"], "instances": [self.by_id[rid] for rid in ids]}
        records = [self._record(rid, responses[rid]) for rid in ids]
        return check_results.evaluate(self._results(records), corpus, self.checker, expected_records=len(ids))

    def test_consistency_capability_needs_the_core_checks_to_pass(self) -> None:
        good = self._evaluate_pairs()
        self.assertTrue(good["passed"], good["failed_ids"])
        self.assertTrue(good["consistency_capability"]["passed"], good["consistency_capability"]["failures"])
        self.assertTrue(all(p["evaluable"] and p["within_half_percent"] for p in good["consistency_pairs"]))
        self.assertIn("CONSISTENCY CAPABILITY: PASS", check_results.render(good))
        first, second = check_results.CONSISTENCY_PAIRS[0]

        def wrong_total(responses):
            responses[second]["tokens"] += 1

        summary = self._evaluate_pairs(wrong_total)
        rows = {row["id"]: row for row in summary["rows"]}
        self.assertEqual(rows[first]["utility"], rows[second]["utility"], "utilities are still equal")
        self.assertEqual(summary["failed_ids"], [second])
        pair = summary["consistency_pairs"][0]
        self.assertEqual((pair["evaluable"], pair["within_half_percent"], pair["L"]), (False, None, None))
        self.assertFalse(summary["consistency_capability"]["passed"])
        self.assertEqual(len(summary["consistency_capability"]["failures"]), 1)
        self.assertIn("not evaluable", summary["consistency_capability"]["failures"][0])
        self.assertIn(f"{second} fails the core checks", summary["consistency_capability"]["failures"][0])
        text = check_results.render(summary)
        self.assertIn("CONSISTENCY CAPABILITY: FAIL (1 of 3 pairs", text)

        def all_wrong(responses):
            for response in responses.values():
                response["tokens"] += 1

        summary = self._evaluate_pairs(all_wrong)
        self.assertFalse(summary["consistency_capability"]["passed"], "the reviewer's reproduction")
        self.assertIn("CONSISTENCY CAPABILITY: FAIL (3 of 3 pairs", check_results.render(summary))

    def test_non_ok_pair_member_is_not_evaluable(self) -> None:
        first = check_results.CONSISTENCY_PAIRS[0][0]
        summary = self._evaluate_pairs(lambda r: r.__setitem__(first, {"status": "infeasible", "reason": "no"}))
        self.assertFalse(summary["consistency_pairs"][0]["evaluable"])
        self.assertFalse(summary["consistency_capability"]["passed"])

    def test_certificate_on_a_record_with_core_problems_does_not_count(self) -> None:
        request = self.by_id[self.profile_id]["request"]
        zero = {"scale": 1, "budget_price": 0, "feature_prices": {fid: 0 for fid in request["features"]}}
        wrong = dict(self._ok_response(self.profile_id), certificate=zero)
        wrong["tokens"] += 1
        summary = self._evaluate_one(self.profile_id, wrong)
        self.assertEqual(summary["failed_ids"], [self.profile_id])
        self.assertEqual(summary["certificates"], [], "no bound is reported for a record that fails the core checks")
        capability = summary["certificate_capability"]
        self.assertFalse(capability["passed"])
        self.assertEqual(capability["failures"],
                         [f"{self.profile_id}: the core checks fail, so a certificate here does not count"])

    def test_malformed_certificate_does_not_fail_the_core_verdict(self) -> None:
        legal = self._ok_response(self.feasible_id)
        self.assertTrue(self._evaluate_one(self.feasible_id, legal)["passed"])
        for label, certificate in (("empty", {}), ("not an object", 7),
                                   ("bad scale", {"scale": 0, "budget_price": 0, "feature_prices": {}})):
            with self.subTest(label=label):
                summary = self._evaluate_one(self.feasible_id, dict(legal, certificate=certificate))
                self.assertTrue(summary["passed"], summary["rows"][0]["problems"])
                self.assertEqual(summary["failed_ids"], [])
                row = summary["rows"][0]
                self.assertEqual((row["verdict"], row["problems"]), ("pass", []))
                self.assertTrue(row["certificate_errors"])
                self.assertTrue(all(e.startswith("certificate:") for e in row["certificate_errors"]))
                self.assertFalse(summary["certificate_capability"]["passed"])
                text = check_results.render(summary)
                self.assertIn("RESULT: PASS (0 of 1 records failed, 0 integrity checks failed)", text)
                self.assertIn("## Optional certificate capability", text)
                self.assertIn("CERTIFICATE CAPABILITY: FAIL", text)
                self.assertIn("certificate:", text.split("## Optional certificate capability")[1])
                self.assertNotIn("certificate:", text.split("## Optional certificate capability")[0])

    def test_core_errors_still_fail_beside_a_malformed_certificate(self) -> None:
        wrong = dict(self._ok_response(self.feasible_id), certificate={})
        wrong["tokens"] += 1
        summary = self._evaluate_one(self.feasible_id, wrong)
        self.assertFalse(summary["passed"])
        self.assertEqual(summary["failed_ids"], [self.feasible_id])

    def test_certificate_gap_is_reported_without_touching_the_core_verdict(self) -> None:
        request = self.by_id[self.profile_id]["request"]
        legal = self._ok_response(self.profile_id)
        zero = {"scale": 1, "budget_price": 0, "feature_prices": {fid: 0 for fid in request["features"]}}
        bound, scale = self.checker.certificate_bound(request, zero)
        self.assertGreater(100 * bound, 105 * legal["utility"] * scale, "the zero-price bound is loose here")
        summary = self._evaluate_one(self.profile_id, dict(legal, certificate=zero))
        self.assertTrue(summary["passed"], summary["rows"][0]["problems"])
        self.assertEqual(summary["certificates"], [{"id": self.profile_id, "U": bound, "s": scale,
                                                    "utility": legal["utility"], "within_5_percent": False}])
        self.assertFalse(summary["certificate_capability"]["passed"])
        text = check_results.render(summary)
        self.assertIn(f"- certificate {self.profile_id}: U={bound}, s={scale}", text)
        self.assertIn("CERTIFICATE CAPABILITY: FAIL", text)
        self.assertIn("CONSISTENCY CAPABILITY: FAIL", text)
        self.assertIn("RESULT: PASS", text)
        missing = self._evaluate_one(self.profile_id, legal)
        self.assertTrue(missing["passed"])
        self.assertFalse(missing["certificate_capability"]["passed"], "no certificate on a profile instance")

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
            shutil.copyfile(supplied("benchmark_inputs.json"), run_dir / "benchmark_inputs.json")
            results = self._results(self._good_records())
            (run_dir / "benchmark_results.json").write_text(json.dumps(results), encoding="utf-8")
            out = run_dir / "summary.json"
            with contextlib.redirect_stdout(io.StringIO()) as text, contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(check_results.main([str(run_dir), "--json", str(out)]), 1)
                self.assertEqual(check_results.main([str(run_dir), "--allow-wrong"]), 0)
                self.assertEqual(check_results.main([str(run_dir / "missing")]), 1)
            self.assertIn("RESULT: FAIL", text.getvalue())
            self.assertFalse(json.loads(out.read_text(encoding="utf-8"))["passed"])


if __name__ == "__main__":
    unittest.main()
