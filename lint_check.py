# -*- coding: utf-8 -*-
"""
lint_check.py - Check Python files exceeding line limits

Usage:
    python lint_check.py           # Scan all .py files
    python lint_check.py --fix    # Show split suggestions for oversized files
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import NamedTuple


class FileInfo(NamedTuple):
    path: Path
    lines: int
    is_test: bool
    is_init: bool


LIMIT_SOFT = 400
# Detect project root: this file lives at <project_root>/lint_check.py
PROJECT_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PROJECT_ROOT / "src" / "atas_market_structure"


def scan_files(root: Path) -> list[FileInfo]:
    results: list[FileInfo] = []
    for py_file in sorted(root.rglob("*.py")):
        rel = py_file.relative_to(root)
        lines = sum(1 for _ in open(py_file, encoding="utf-8"))
        is_test = "/tests/" in str(rel) or rel.name.startswith("test_")
        is_init = rel.name == "__init__.py"
        results.append(FileInfo(path=rel, lines=lines, is_test=is_test, is_init=is_init))
    return results


def assess_file(info: FileInfo) -> str | None:
    if info.is_test or info.is_init:
        return None
    if info.lines > LIMIT_SOFT:
        return "🟡 超过软性上限"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="检查 Python 文件行数")
    parser.add_argument("--fix", action="store_true", help="显示拆分建议")
    args = parser.parse_args()

    files = scan_files(SRC_ROOT)
    total = len(files)
    over_soft = [f for f in files if f.lines > LIMIT_SOFT]

    print(f"[PASS] {total} Python files scanned")
    print(f"Soft limit: {LIMIT_SOFT} lines")
    print()

    if not over_soft:
        print("[OK] All files are within the soft limit")
        return 0

    print(f"[WARN] {len(over_soft)} file(s) exceed {LIMIT_SOFT} lines:")
    print()

    for info in over_soft:
        status = assess_file(info)
        print(f"[WARN] {info.path} ({info.lines} lines)")
        if args.fix and not info.is_test and not info.is_init:
            print(f"   -> Suggestion: split this file. See .cursor/rules/code-organization.md")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
