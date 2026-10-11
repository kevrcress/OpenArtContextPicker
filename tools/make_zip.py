"""Write a deterministic ZIP of a package directory with files at the archive root.

Usage: python3.11 tools/make_zip.py <dir> <zip-path>

Entries are sorted, carry a fixed timestamp and are deflated, so the same
directory content always gives the same archive bytes. Dot-directories such as
``.claude-hve-tracking/`` are archived; caches, compiled files and a stray
``gate.log`` are not.
"""

from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

FIXED_TIME = (1980, 1, 1, 0, 0, 0)
EXCLUDED_NAMES = {"__pycache__", ".DS_Store", "gate.log"}
EXCLUDED_SUFFIXES = {".pyc"}


def package_entries(root: Path, skip: Path | None = None) -> list[tuple[str, Path]]:
    """Sorted ``(archive name, file)`` pairs for every packaged file under ``root``."""
    entries = []
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if not path.is_file() or any(part in EXCLUDED_NAMES for part in rel.parts):
            continue
        if rel.suffix in EXCLUDED_SUFFIXES:
            continue
        if skip is not None and path.resolve() == skip:
            continue
        entries.append((rel.as_posix(), path))
    return sorted(entries)


def make_zip(root: Path, zip_path: Path) -> int:
    """Write the archive and return the number of entries."""
    root = root.resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"not a directory: {root}")
    entries = package_entries(root, skip=zip_path.resolve())
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, path in entries:
            info = zipfile.ZipInfo(name, date_time=FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            mode = 0o755 if path.stat().st_mode & 0o100 else 0o644
            info.external_attr = (0o100000 | mode) << 16
            archive.writestr(info, path.read_bytes(), compresslevel=9)
    return len(entries)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic ZIP with files at the archive root.")
    parser.add_argument("dir", type=Path)
    parser.add_argument("zip_path", type=Path)
    args = parser.parse_args(argv)
    try:
        count = make_zip(args.dir, args.zip_path)
    except OSError as exc:
        print(f"make_zip: {exc}", file=sys.stderr)
        return 1
    print(f"{args.zip_path}: {count} entries, {args.zip_path.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
