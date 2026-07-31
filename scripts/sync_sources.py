#!/usr/bin/env python3
"""Synchronize canonical package sources to Hermes' root plugin layout."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAIRS = (
    (ROOT / "src" / "recall_memory_hermes" / "__init__.py", ROOT / "__init__.py"),
    (ROOT / "src" / "recall_memory_hermes" / "memory_policy.py", ROOT / "memory_policy.py"),
)


def check() -> int:
    mismatches = []
    for source, target in PAIRS:
        if not target.exists() or source.read_bytes() != target.read_bytes():
            mismatches.append(f"{target.relative_to(ROOT)} != {source.relative_to(ROOT)}")
    if mismatches:
        print("SOURCE_SYNC_FAILED")
        for mismatch in mismatches:
            print(f"- {mismatch}")
        print("Run: python scripts/sync_sources.py")
        return 1
    print("SOURCE_SYNC_OK")
    return 0


def sync() -> int:
    for source, target in PAIRS:
        shutil.copyfile(source, target)
        print(f"SYNCED {source.relative_to(ROOT)} -> {target.relative_to(ROOT)}")
    return check()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if generated root files drift")
    args = parser.parse_args()
    return check() if args.check else sync()


if __name__ == "__main__":
    raise SystemExit(main())
