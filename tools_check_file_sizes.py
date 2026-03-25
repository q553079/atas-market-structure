#!/usr/bin/env python3
"""Lightweight giant-file guard for atas-market-structure.

Run manually or from CI:
    python tools_check_file_sizes.py
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOTS = [Path("src/atas_market_structure"), Path("tests")]

SOFT = {
    "service": 500,
    "repository": 500,
    "route": 300,
    "model": 300,
    "test": 400,
}
HARD = {
    "service": 800,
    "repository": 800,
    "route": 500,
    "model": 450,
    "test": 700,
}


def classify(path: Path) -> str:
    name = path.name.lower()
    full = str(path).lower()
    if full.startswith("tests") or "/tests/" in full:
        return "test"
    if "repository" in name:
        return "repository"
    if "route" in name or "app_routes" in full:
        return "route"
    if "model" in name or "/models/" in full:
        return "model"
    return "service"


def line_count(path: Path) -> int:
    try:
        return path.read_text(encoding="utf-8").count("\n") + 1
    except Exception:
        return 0


def main() -> int:
    hard_failures: list[tuple[str, int, int]] = []
    soft_warnings: list[tuple[str, int, int]] = []

    for root in ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            kind = classify(path)
            lines = line_count(path)
            if lines > HARD[kind]:
                hard_failures.append((str(path), lines, HARD[kind]))
            elif lines > SOFT[kind]:
                soft_warnings.append((str(path), lines, SOFT[kind]))

    if soft_warnings:
        print("Soft-limit warnings:")
        for path, lines, limit in sorted(soft_warnings, key=lambda x: x[1], reverse=True):
            print(f"  WARN {path}: {lines} lines (soft limit {limit})")

    if hard_failures:
        print("\nHard-limit failures:")
        for path, lines, limit in sorted(hard_failures, key=lambda x: x[1], reverse=True):
            print(f"  FAIL {path}: {lines} lines (hard limit {limit})")
        return 1

    print("No hard-limit violations detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
