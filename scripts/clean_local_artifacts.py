#!/usr/bin/env python
"""Clean local generated artifacts in repository root.

This script only removes local caches/reports/build outputs that should not be
committed. It is safe to run repeatedly.
"""

from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

TARGETS = [
    ".coverage",
    "coverage.xml",
    "htmlcov",
    "reports",
    "build/pyinstaller",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
]


def remove_path(path: Path) -> None:
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
        print(f"removed dir: {path.relative_to(ROOT)}")
    else:
        path.unlink(missing_ok=True)
        print(f"removed file: {path.relative_to(ROOT)}")


def main() -> None:
    print("Cleaning local generated artifacts...")
    for item in TARGETS:
        remove_path(ROOT / item)
    print("Done.")


if __name__ == "__main__":
    main()
