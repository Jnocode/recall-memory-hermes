#!/usr/bin/env python3
"""Smoke-test the installed wheel without treating it as a Hermes plugin install."""

from __future__ import annotations

import sys
import types
from pathlib import Path


def _is_repository_source(module_path: Path, repository: Path) -> bool:
    """Return true only for imports from the canonical ``src`` package tree."""
    canonical_package = (repository / "src" / "recall_memory_hermes").resolve()
    resolved_module = module_path.resolve()
    return resolved_module == canonical_package or canonical_package in resolved_module.parents


def main() -> None:
    agent = types.ModuleType("agent")
    memory_provider = types.ModuleType("agent.memory_provider")

    class MemoryProvider:
        """Minimal import-only stand-in for Hermes' provider ABC."""

    memory_provider.MemoryProvider = MemoryProvider
    agent.memory_provider = memory_provider
    sys.modules.setdefault("agent", agent)
    sys.modules.setdefault("agent.memory_provider", memory_provider)

    import recall_memory_hermes

    module_path = Path(recall_memory_hermes.__file__).resolve()
    repository = Path(__file__).resolve().parents[1]
    if _is_repository_source(module_path, repository):
        raise RuntimeError(f"expected installed wheel, imported repository source: {module_path}")
    if recall_memory_hermes.__version__ != "0.3.0":
        raise RuntimeError(f"unexpected wheel version: {recall_memory_hermes.__version__}")
    print(f"WHEEL_LIBRARY_SMOKE_OK version={recall_memory_hermes.__version__}")


if __name__ == "__main__":
    main()
