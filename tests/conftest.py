"""Shared test doubles for the Hermes MemoryProvider contract."""

from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class MemoryProvider:
    """Minimal ABC-compatible base used outside a Hermes installation."""


agent_module = types.ModuleType("agent")
memory_provider_module = types.ModuleType("agent.memory_provider")
memory_provider_module.MemoryProvider = MemoryProvider
agent_module.memory_provider = memory_provider_module
sys.modules.setdefault("agent", agent_module)
sys.modules.setdefault("agent.memory_provider", memory_provider_module)
