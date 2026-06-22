"""recall-memory-hermes: Hermes Agent memory provider plugin.

This plugin adapts recall-memory (SAG-based, sqlite-vec + FTS5)
into Hermes Agent's memory provider interface, with optional
Honcho fallback for the bridge period.

Usage:
    hermes memory setup  # select 'recall' as provider
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Provider Class ───────────────────────────────────────────────────────────

class RecallMemoryProvider:
    """Hermes memory provider backed by recall-memory."""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self.db_path = self.config.get("db_path", self._auto_detect_db())
        self.embed_url = self.config.get("embed_url", "http://127.0.0.1:1234")
        self.fallback_honcho = self.config.get("fallback_honcho", True)
        self.fallback_honcho_url = self.config.get("fallback_honcho_url", "http://localhost:8082")

        self._store = None
        self._honcho_client = None
        self._initialized = False

    def _auto_detect_db(self) -> str:
        """Auto-detect recall DB path."""
        candidates = [
            os.path.expanduser("~/.recall/recall_p0.db"),
            os.path.expanduser("~/recall/recall_p0.db"),
            os.path.join(os.getcwd(), "recall_p0.db"),
        ]
        for path in candidates:
            if os.path.exists(path):
                return path
        # Fallback to cwd
        return os.path.join(os.getcwd(), "recall_p0.db")

    def initialize(self):
        """Initialize the provider. Called by Hermes at session start."""
        if self._initialized:
            return

        # Import recall (lazy import so plugin can be installed without recall)
        try:
            from recall.store import SQLiteStore
            self._store = SQLiteStore(self.db_path)
            logger.info(f"✅ recall store opened: {self.db_path} ({self._store.count()} memories)")
        except ImportError as e:
            logger.error(f"❌ recall-memory not installed: {e}")
            raise

        self._initialized = True

    # ─── Core API ─────────────────────────────────────────────────────────────

    def search(self, query: str, k: int = 5) -> list[dict]:
        """Search memories. Uses recall first, falls back to Honcho if <3 results."""
        if not self._initialized:
            self.initialize()

        results = self._recall_search(query, k)

        # Conditional fallback: if recall returns <3 results, try Honcho
        if self.fallback_honcho and len(results) < min(3, k):
            honcho_results = self._honcho_search(query, k - len(results))
            results.extend(honcho_results)

        return results

    def store(self, content: str, metadata: Optional[dict] = None) -> str:
        """Store a memory. Only writes to recall (no dual-write to Honcho)."""
        if not self._initialized:
            self.initialize()

        from recall.store import Memory
        from datetime import datetime, timezone

        mem = Memory(
            content=content,
            session_id=(metadata or {}).get("session_id", ""),
            tag=(metadata or {}).get("tag", "episodic"),
            timestamp=datetime.now(timezone.utc),
        )
        mem_id = self._store.add(mem)
        logger.info(f"✅ stored: {mem_id}")
        return mem_id

    def stats(self) -> dict:
        """Return memory statistics."""
        if not self._initialized:
            self.initialize()
        return {
            "memories": self._store.count(),
            "keywords": self._count_keywords(),
        }

    # ─── Internal ─────────────────────────────────────────────────────────────

    def _recall_search(self, query: str, k: int) -> list[dict]:
        """Search recall using 3-path RRF retrieval."""
        try:
            from recall.retrieve import retrieve_relevant
            memories = retrieve_relevant(query, self._store, k=k)
            return [
                {"id": m.id, "content": m.content, "score": 1.0, "source": "recall"}
                for m in memories
            ]
        except Exception as e:
            logger.warning(f"recall search failed: {e}")
            return []

    def _honcho_search(self, query: str, k: int) -> list[dict]:
        """Fallback: search Honcho via API."""
        try:
            import httpx
            r = httpx.get(
                f"{self.fallback_honcho_url}/v3/workspaces/hermes-agent/search",
                params={"q": query, "limit": k},
                timeout=5.0,
            )
            if r.status_code != 200:
                return []
            data = r.json()
            results = data.get("results", data.get("hits", []))
            return [
                {"id": r.get("id", ""), "content": r.get("content", ""),
                 "score": 0.5, "source": "honcho"}
                for r in results[:k]
            ]
        except Exception as e:
            logger.warning(f"honcho fallback failed: {e}")
            return []

    def _count_keywords(self) -> int:
        """Count keywords in recall store."""
        import sqlite3
        try:
            conn = sqlite3.connect(self.db_path)
            row = conn.execute("SELECT COUNT(*) FROM keywords").fetchone()
            conn.close()
            return row[0] if row else 0
        except:
            return 0


# ─── Plugin Entry Point ──────────────────────────────────────────────────────

def create_provider(config: Optional[dict] = None) -> RecallMemoryProvider:
    """Factory function called by Hermes plugin system."""
    return RecallMemoryProvider(config)
