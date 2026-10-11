"""Assemble the delivery package directory from the repository.

Usage: python3.11 tools/build_package.py --out build/pkg [--source REPO] [--verify-results]

The package mirrors the ZIP root: solver modules, ``tests/``, ``tools/``, the
README, the recorder output when present, and byte copies of the three supplied
files from ``resources/``. The build refuses to run when a supplied file no
longer matches its recorded SHA-256. With ``--verify-results`` (the final build)
the results file, the run log and the README are required and every packaged
``*.py`` must match ``python_sources_after`` exactly.

The package is assembled in a temporary directory beside ``--out`` and renamed
to ``--out`` only after every check has passed, so a failed build leaves no
output directory behind.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

# SHA-256 of the supplied files as received (integrity baseline from the research document).
RESOURCE_BASELINE = {
    "benchmark_runner.py": "87694477eca9636ed78766d4473821befb9d388bf2444b2e1b5310f5e6ca5943",
    "benchmark_inputs.json": "164ea460ed919a4e5e365c5357b9d53606f8f5fb53df8c238664c8117eae541c",
}
RESOURCE_COPIES = ("benchmark_runner.py", "benchmark_inputs.json", "director_session.json")
TREES = ("tests", "tools")
OPTIONAL_ROOT_FILES = ("README.md", "benchmark_results.json", "benchmark_run.log")
EXCLUDED_NAMES = {"__pycache__", ".DS_Store", "gate.log", ".git", ".claude", ".claude-hve-tracking"}
RESULTS_NAME = "benchmark_results.json"
# Required in the package by --verify-results; optional in a pre-run staging build.
REQUIRED_FINAL_FILES = (RESULTS_NAME, "benchmark_run.log", "README.md")


class PackageError(Exception):
    """The package cannot be built or does not match the recorded run."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _excluded(path: Path) -> bool:
    return path.suffix == ".pyc" or any(part in EXCLUDED_NAMES for part in path.parts)


def check_resources(source: Path) -> None:
    """Raise ``PackageError`` unless every supplied file exists and matches the baseline."""
    for name in RESOURCE_COPIES:
        path = source / "resources" / name
        if not path.is_file():
            raise PackageError(f"missing supplied file: {path}")
        expected = RESOURCE_BASELINE.get(name)
        if expected is not None and sha256_file(path) != expected:
            raise PackageError(f"resources/{name} differs from the baseline: got {sha256_file(path)}, want {expected}")


def planned_files(source: Path) -> dict[str, Path]:
    """Map package-relative POSIX paths to their source files."""
    plan: dict[str, Path] = {}
    for path in sorted(source.glob("*.py")):
        if path.is_file():
            plan[path.name] = path
    for tree in TREES:
        root = source / tree
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            rel = path.relative_to(source)
            if path.is_file() and not _excluded(rel):
                plan[rel.as_posix()] = path
    for name in OPTIONAL_ROOT_FILES:
        if (source / name).is_file():
            plan[name] = source / name
    for name in RESOURCE_COPIES:
        plan[name] = source / "resources" / name
    return plan


def require_final_files(present) -> None:
    """Raise ``PackageError`` unless every file the final package must carry is in ``present``."""
    missing = [name for name in REQUIRED_FINAL_FILES if name not in present]
    if missing:
        raise PackageError("--verify-results needs these files in the package, missing: " + ", ".join(missing))


def verify_results(out: Path) -> None:
    """Raise unless the final deliverables exist and the Python sources are exactly those recorded."""
    require_final_files({name for name in REQUIRED_FINAL_FILES if (out / name).is_file()})
    results_path = out / RESULTS_NAME
    try:
        text = results_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PackageError(f"cannot read {RESULTS_NAME}: {exc}") from exc
    try:
        recorded = json.loads(text)["python_sources_after"]
    except (ValueError, KeyError, TypeError) as exc:
        raise PackageError(f"{RESULTS_NAME} has no readable python_sources_after: {exc!r}") from exc
    if not isinstance(recorded, dict):
        raise PackageError(f"{RESULTS_NAME}: python_sources_after is not an object")
    actual = {}
    for path in sorted(out.rglob("*.py")):
        if "__pycache__" not in path.parts and path.is_file():
            actual[path.relative_to(out).as_posix()] = sha256_file(path)
    problems = [f"not in the recorded run: {name}" for name in sorted(set(actual) - set(recorded))]
    problems += [f"recorded but not in the package: {name}" for name in sorted(set(recorded) - set(actual))]
    problems += [f"changed since the recorded run: {name}" for name in sorted(set(actual) & set(recorded))
                 if actual[name] != recorded[name]]
    if problems:
        raise PackageError("package does not match python_sources_after:\n  " + "\n  ".join(problems))


def _fill(plan: dict[str, Path], stage: Path, *, verify: bool) -> None:
    """Copy ``plan`` into ``stage`` and run every post-copy check there."""
    for rel, src in plan.items():
        dest = stage / rel
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        except OSError as exc:
            raise PackageError(f"cannot copy {rel} into the package: {exc}") from exc
    for name, expected in RESOURCE_BASELINE.items():
        if sha256_file(stage / name) != expected:
            raise PackageError(f"copied {name} does not match the baseline")
    if verify:
        verify_results(stage)


def build(source: Path, out: Path, *, verify: bool = False) -> list[str]:
    """Assemble the package beside ``out`` and rename it to ``out`` once every check passes.

    Returns the sorted package paths. On any failure the temporary directory is
    removed and ``out`` is left as it was (absent, or empty).
    """
    source = source.resolve()
    out = out.resolve()
    check_resources(source)
    if not (source / "context_solver.py").is_file():
        raise PackageError(f"missing entrypoint: {source / 'context_solver.py'}")
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise PackageError(f"output directory is not empty: {out}")
    plan = planned_files(source)
    if verify:
        require_final_files(plan)  # fail before anything is copied
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=f".{out.name}.tmp-", dir=out.parent))
    except OSError as exc:
        raise PackageError(f"cannot create a temporary directory beside {out}: {exc}") from exc
    try:
        _fill(plan, stage, verify=verify)
        os.chmod(stage, 0o755)
        if out.exists():
            out.rmdir()  # checked empty above
        os.replace(stage, out)
    except BaseException as exc:
        shutil.rmtree(stage, ignore_errors=True)
        if isinstance(exc, OSError):
            raise PackageError(f"cannot finish the package at {out}: {exc}") from exc
        raise
    return sorted(plan)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assemble the delivery package directory.")
    parser.add_argument("--out", required=True, type=Path, help="empty or new directory to fill")
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parent.parent,
                        help="repository root (default: the parent of tools/)")
    parser.add_argument("--verify-results", action="store_true",
                        help="final build: require benchmark_results.json, benchmark_run.log and README.md, and fail "
                             "unless every packaged .py matches python_sources_after")
    args = parser.parse_args(argv)
    try:
        files = build(args.source, args.out, verify=args.verify_results)
    except (PackageError, OSError) as exc:
        print(f"build_package: {exc}; no output was written to {args.out}", file=sys.stderr)
        return 1
    if "README.md" not in files:
        print("build_package: warning: no README.md in the source tree", file=sys.stderr)
    print(f"packaged {len(files)} files into {args.out.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
