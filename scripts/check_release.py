#!/usr/bin/env python3
"""Fail release builds when version or generated-source metadata drifts."""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_DEPS = ["recall-sqlite==0.2.0", "httpx>=0.27,<1"]
RETIRED_TAGS = {"v0.2.1"}


def _source_version() -> str:
    source = (ROOT / "src" / "recall_memory_hermes" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', source, re.MULTILINE)
    if not match:
        raise ValueError("canonical source has no __version__")
    return match.group(1)


def check(tag: str = "") -> list[str]:
    errors: list[str] = []
    if tag in RETIRED_TAGS:
        errors.append(f"retired tag must never be reused: {tag}")
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    manifest = yaml.safe_load((ROOT / "plugin.yaml").read_text(encoding="utf-8"))
    package_version = str(pyproject["project"]["version"])
    versions = {
        "pyproject": package_version,
        "plugin.yaml": str(manifest.get("version", "")),
        "source": _source_version(),
    }
    if tag:
        versions["tag"] = tag.removeprefix("v")
    if len(set(versions.values())) != 1:
        errors.append(f"version mismatch: {versions}")

    project_deps = list(pyproject["project"].get("dependencies", []))
    manifest_deps = list(manifest.get("pip_dependencies", []))
    if project_deps != EXPECTED_DEPS:
        errors.append(f"pyproject dependencies mismatch: {project_deps}")
    if manifest_deps != EXPECTED_DEPS:
        errors.append(f"plugin dependencies mismatch: {manifest_deps}")

    for source, target in (
        (ROOT / "src" / "recall_memory_hermes" / "__init__.py", ROOT / "__init__.py"),
        (ROOT / "src" / "recall_memory_hermes" / "memory_policy.py", ROOT / "memory_policy.py"),
    ):
        if source.read_bytes() != target.read_bytes():
            errors.append(f"source drift: {target.name} != {source.relative_to(ROOT)}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", default="", help="release tag, e.g. v0.3.0")
    args = parser.parse_args()
    errors = check(args.tag)
    if errors:
        print("RELEASE_CHECK_FAILED")
        for error in errors:
            print(f"- {error}")
        return 1
    print("RELEASE_CHECK_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
