"""recall-memory-hermes: Hermes Agent memory provider plugin.

Session-aware, peer-contextual, tag-filtered retrieval backed by
recall-memory (SAG-based, sqlite-vec + FTS5 + keyword SQL JOIN).
Optional Honcho fallback during bridge period.

Usage:
    hermes memory setup  # select 'recall' as provider
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

RECALL_DB_PATH = "D:/Workspace/03_Dev_Projects/recall/recall_p0.db"


class RecallMemoryProvider:
    """Hermes memory provider backed by recall-memory (SAG-based)."""

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self.db_path = self.config.get("db_path", RECALL_DB_PATH)
        self.embed_url = self.config.get("embed_url", "http://127.0.0.1:1234")
        self.fallback_honcho = self.config.get("fallback_honcho", False)
        self.fallback_honcho_url = self.config.get(
            "fallback_honcho_url", "http://localhost:8082"
        )
        self._store = None
        self._initialized = False

    # ─── Lifecycle ──────────────────────────────────────────────────────────

    def initialize(self):
        if self._initialized:
            return
        try:
            from recall.store import SQLiteStore
            self._store = SQLiteStore(self.db_path)
            count = self._store.count()
            logger.info(f"✅ recall: {self.db_path} ({count} memories)")
        except ImportError as e:
            logger.error(f"❌ recall-memory not installed: {e}")
            raise
        self._initialized = True

    # ─── Core API ───────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        k: int = 5,
        session_id: Optional[str] = None,
        peer: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> list[dict]:
        """Search memories with session/peer/tag context.

        Args:
            query: Search text.
            k: Max results.
            session_id: Scope to a specific session.
            peer: 'user' or 'agent' - scope to peer type.
            tag: Filter by tag (episodic, semantic, etc.).

        Returns:
            List of {id, content, score, source, session_id, tag}
        """
        if not self._initialized:
            self.initialize()

        # Phase 1: recall 3-path RRF
        results = self._recall_search(query, k, session_id=session_id, tag=tag)

        # Phase 2: Add peer-based boost (user memories ranked higher for user queries)
        if peer and results:
            self._apply_peer_boost(results, peer)

        # Conditional Honcho fallback when recall returns few results
        if self.fallback_honcho and len(results) < min(3, k):
            honcho_results = self._honcho_search(query, k - len(results))
            results.extend(honcho_results)

        return results[:k]

    def store(
        self,
        content: str,
        metadata: Optional[dict] = None,
    ) -> str:
        """Store a memory. No dual-write to Honcho.

        Args:
            content: Memory text.
            metadata: Optional dict with session_id, tag, peer.

        Returns:
            Memory ID string.
        """
        if not self._initialized:
            self.initialize()

        from recall.store import Memory
        from datetime import datetime, timezone

        meta = metadata or {}
        mem = Memory(
            content=content,
            session_id=meta.get("session_id", ""),
            tag=meta.get("tag", "episodic"),
            timestamp=datetime.now(timezone.utc),
        )
        mem_id = self._store.add(mem)
        logger.info(f"✅ stored: {mem_id}")
        return mem_id

    def stats(self) -> dict:
        if not self._initialized:
            self.initialize()
        return {
            "memories": self._store.count(),
            "keywords": self._count_keywords(),
        }

    def get_by_session(self, session_id: str) -> list[dict]:
        """Get all memories for a session."""
        if not self._initialized:
            self.initialize()
        memories = self._store.get_by_session(session_id)
        return [
            {"id": m.id, "content": m.content, "score": 1.0, "source": "recall",
             "session_id": m.session_id, "tag": m.tag}
            for m in memories
        ]

    def delete(self, memory_id: str) -> bool:
        if not self._initialized:
            self.initialize()
        return self._store.delete(memory_id)

    # ─── Internal: Recall search ───────────────────────────────────────────

    def _recall_search(
        self,
        query: str,
        k: int,
        session_id: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> list[dict]:
        """Search recall via 3-path RRF, optionally scoped."""
        try:
            from recall.retrieve import retrieve_relevant

            memories = retrieve_relevant(
                query,
                self._store,
                k=k * 2,  # fetch more for post-filtering
                tag_filter=tag,
            )
            results = [
                {
                    "id": m.id,
                    "content": m.content,
                    "score": 1.0,
                    "source": "recall",
                    "session_id": m.session_id,
                    "tag": m.tag,
                }
                for m in memories
            ]

            # Post-filter by session_id if specified
            if session_id and results:
                scoped = [r for r in results if r["session_id"] == session_id]
                if scoped:
                    return scoped[:k]
                # If no session-scoped results, return global results
            return results[:k]

        except Exception as e:
            logger.warning(f"recall search failed: {e}")
            return []

    # ─── Internal: Peer boost ──────────────────────────────────────────────

    def _apply_peer_boost(self, results: list[dict], peer: str):
        """Boost memories matching the current peer (user/agent).

        Simple heuristic: peer='user' boosts memories without session_id
        (user-stored facts), peer='agent' boosts agent-generated memories.
        """
        for r in results:
            if peer == "user" and not r.get("session_id"):
                r["score"] = r.get("score", 1.0) * 1.2
            elif peer == "agent" and r.get("session_id", "").startswith("agent_"):
                r["score"] = r.get("score", 1.0) * 1.2

    # ─── Internal: Honcho fallback ─────────────────────────────────────────

    def _honcho_search(self, query: str, k: int) -> list[dict]:
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
            hits = data.get("results", data.get("hits", []))
            return [
                {
                    "id": h.get("id", ""),
                    "content": h.get("content", ""),
                    "score": 0.5,
                    "source": "honcho",
                    "session_id": "",
                    "tag": "",
                }
                for h in hits[:k]
            ]
        except Exception as e:
            logger.warning(f"honcho fallback failed: {e}")
            return []

    # ─── Internal: Helpers ─────────────────────────────────────────────────

    def _count_keywords(self) -> int:
        import sqlite3
        try:
            conn = sqlite3.connect(self.db_path)
            row = conn.execute("SELECT COUNT(*) FROM keywords").fetchone()
            conn.close()
            return row[0] if row else 0
        except Exception:
            return 0


# ─── Plugin Entry Point ──────────────────────────────────────────────────

def create_provider(config: Optional[dict] = None) -> RecallMemoryProvider:
    """Factory function called by Hermes plugin system."""
    return RecallMemoryProvider(config)
