"""recall-memory-hermes: Hermes Agent memory provider plugin.

Hermes MemoryProvider ABC implementation backed by recall-memory
(SAG-based, sqlite-vec + FTS5 + keyword SQL JOIN, 3-path RRF).
Session-aware, peer-contextual, tag-filtered retrieval.
Optional Honcho fallback (OFF by default).
"""

import os
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from agent.memory_provider import MemoryProvider

logger = logging.getLogger(__name__)

_HERMES_HOME = os.environ.get("HERMES_HOME", os.path.expanduser("~/.hermes"))
RECALL_DB_PATH = os.path.join(_HERMES_HOME, "recall.db")


class RecallMemoryProvider(MemoryProvider):
    """Hermes memory provider backed by recall-memory (SAG-based)."""

    @property
    def name(self) -> str:
        return "recall"

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self.db_path = self.config.get("db_path", RECALL_DB_PATH)
        self.embed_url = self.config.get("embed_url", "http://127.0.0.1:1234")
        self.fallback_honcho = self.config.get("fallback_honcho", False)
        self.fallback_honcho_url = self.config.get(
            "fallback_honcho_url", "http://localhost:8082"
        )
        self._store = None
        self._memory_count = 0

    # ─── ABC Required: Core lifecycle ───────────────────────────────────────

    def is_available(self) -> bool:
        """Check if recall-sqlite is installed and DB accessible."""
        try:
            import recall  # noqa
        except ImportError:
            logger.warning("recall-sqlite not installed — run: pip install recall-sqlite")
            return False
        # Auto-init DB if missing
        if not os.path.exists(self.db_path):
            from recall.store import SQLiteStore
            try:
                _store = SQLiteStore(self.db_path)
                logger.info(f"Created new recall DB at {self.db_path}")
                return True
            except Exception as e:
                logger.warning(f"Failed to create recall DB: {e}")
                return False
        return True

    def initialize(self, session_id: str = "", **kwargs) -> None:
        """Connect to recall DB, warm up."""
        if self._store is not None:
            return
        from recall.store import SQLiteStore
        from recall.embed import is_loaded
        self._session_id = session_id
        self._store = SQLiteStore(self.db_path)
        self._memory_count = self._store.count()
        logger.info(f"recall initialized: {self.db_path} ({self._memory_count} memories)")
        if not is_loaded():
            logger.warning("LM Studio embedding not available — ANN search disabled. Start LM Studio with nomic-embed-text-v1.5 on port 1234")

    def shutdown(self):
        """Clean shutdown."""
        self._store = None
        logger.info("recall provider shut down")

    # ─── ABC Required: System prompt ────────────────────────────────────────

    def system_prompt_block(self) -> str:
        """Static block for system prompt describing recall capabilities."""
        if not self._store:
            return ""
        return (
            f"You have access to recall-memory: a persistent SAG-based memory store "
            f"with {self._memory_count} memories. "
            f"Use `memory recall <query>` to search across sessions."
        )

    # ─── ABC Required: Prefetch / Sync ──────────────────────────────────────

    def prefetch(self, query: str, session_id: str = "") -> str:
        """Called before each turn. Search recall for relevant memories."""
        if not self._store:
            self.initialize()
        if not query or not query.strip():
            return ""
        try:
            from recall.retrieve import retrieve_relevant
            memories = retrieve_relevant(query, self._store, k=5)
            if not memories:
                return ""
            lines = [f"🔍 找到相關記憶："]
            for m in memories[:5]:
                tag = f"[{m.tag}]" if m.tag else ""
                lines.append(f"  {tag} {m.content[:120]}")
            return "\n".join(lines)
        except Exception as e:
            logger.debug(f"prefetch failed: {e}")
            return ""

    def sync_turn(
        self,
        user_content: str,
        assistant_content: str,
        session_id: str = "",
        messages: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Called after each turn. Store the turn in recall."""
        if not self._store:
            self.initialize()
        if not user_content or not user_content.strip():
            return
        from recall.store import Memory
        from recall.embed import embed
        content = user_content[:500]
        mem = Memory(
            content=content,
            session_id=session_id,
            tag="episodic",
            timestamp=datetime.now(timezone.utc),
            embedding=embed(content),
        )
        try:
            self._store.add(mem)
        except Exception as e:
            logger.debug(f"sync_turn store failed: {e}")

    # ─── ABC Required: Tools ───────────────────────────────────────────────

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Expose memory recall/write tools to the model."""
        return [
            {
                "name": "memory_recall",
                "description": "Search persistent memory across sessions. Returns relevant memories for context.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query to find relevant memories",
                        },
                        "k": {
                            "type": "integer",
                            "description": "Number of results to return",
                            "default": 5,
                        },
                    },
                    "required": ["query"],
                },
            },
        ]

    def handle_tool_call(self, tool_name: str, args: dict, **kwargs) -> str:
        """Dispatch tool calls to the appropriate method."""
        if tool_name == "memory_recall":
            return self._handle_recall_tool(args)
        return f"Unknown tool: {tool_name}"

    def _handle_recall_tool(self, args: dict) -> str:
        """Handle memory_recall tool call."""
        query = args.get("query", "")
        k = args.get("k", 5)
        if not self._store:
            self.initialize()
        try:
            from recall.retrieve import retrieve_relevant
            memories = retrieve_relevant(query, self._store, k=k)
            if not memories:
                return "未找到相關記憶。"
            lines = [f"找到 {len(memories)} 條相關記憶："]
            for m in memories[:k]:
                lines.append(f"- {m.content[:200]}")
            return "\n".join(lines)
        except Exception as e:
            return f"搜尋失敗: {e}"

    # ─── ABC Optional: Mirror writes ────────────────────────────────────────

    def on_memory_write(
        self,
        action: str,
        target: str,
        content: str,
        metadata: Optional[dict] = None,
    ) -> None:
        """Mirror built-in memory tool writes to recall."""
        if not self._store:
            self.initialize()
        from recall.store import Memory
        from recall.embed import embed
        mem = Memory(
            content=content[:500],
            session_id=(metadata or {}).get("session_id", ""),
            tag="semantic" if action in ("replace",) else "episodic",
            timestamp=datetime.now(timezone.utc),
            embedding=embed(content[:500]),
        )
        try:
            self._store.add(mem)
        except Exception as e:
            logger.debug(f"on_memory_write failed: {e}")


# ─── Hermes Plugin Entry Point ───────────────────────────────────────────────

def register(ctx):
    """Register the recall memory provider with Hermes plugin system."""
    provider = RecallMemoryProvider()
    ctx.register_memory_provider(provider)
