"""Hermes memory-provider plugin backed by recall-sqlite."""

from __future__ import annotations

import importlib
import importlib.util
import hashlib
import logging
import os
import re
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from agent.memory_provider import MemoryProvider

try:
    from .memory_policy import (
        build_builtin_content,
        build_semantic_content,
        card_body,
        extract_type,
        infer_project,
        rank_project_candidates,
        should_store_turn,
    )
except ImportError:
    # Direct-file loaders (including pytest's root package collector) provide
    # no package anchor. Normal package import errors must remain visible.
    if __package__:
        raise
    from memory_policy import (  # type: ignore[no-redef]
        build_builtin_content,
        build_semantic_content,
        card_body,
        extract_type,
        infer_project,
        rank_project_candidates,
        should_store_turn,
    )

logger = logging.getLogger(__name__)

__version__ = "0.3.0"
PROVIDER_NAME = "recall-memory-hermes"
PIP_DEPENDENCIES = ("recall-sqlite==0.2.0", "httpx>=0.27,<1")
DEFAULT_EMBED_URL = "http://127.0.0.1:11434"
DEFAULT_EMBED_MODEL = "nomic-embed-text"
DEFAULT_CANDIDATE_MULTIPLIER = 8
MIRROR_SCAN_LIMIT = 10_000
_EMBED_CONFIG_LOCK = threading.RLock()
_URL_CREDENTIALS = re.compile(r"(https?://)[^/@\s]+@", re.IGNORECASE)


def _safe_install_detail(value: Any) -> str:
    detail = _URL_CREDENTIALS.sub(r"\1***@", str(value or "installation failed"))
    return detail[:300]


def _recall_is_importable() -> bool:
    """Check importability without importing Recall or touching its database."""

    try:
        return importlib.util.find_spec("recall") is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _lazy_installer_is_importable() -> bool:
    try:
        return importlib.util.find_spec("tools.lazy_deps") is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return "tools.lazy_deps" in sys.modules


def _ensure_runtime_dependencies() -> None:
    """Import Recall or install the plugin's fixed dependency set safely."""

    try:
        importlib.import_module("recall")
        return
    except ImportError:
        # A present Recall package can still be unusable after an environment
        # rebuild if one of its transitive wheels disappeared. Reinstalling the
        # fixed manifest set is safe and repairs both states.
        pass

    try:
        lazy_module = sys.modules.get("tools.lazy_deps")
        if lazy_module is None:
            lazy_module = importlib.import_module("tools.lazy_deps")
        install_specs = lazy_module.install_specs
    except (AttributeError, ImportError, ModuleNotFoundError) as exc:
        raise RuntimeError(
            "Recall dependency is missing and Hermes' safe lazy installer is unavailable. "
            "Run in the Hermes environment: pip install recall-sqlite==0.2.0 'httpx>=0.27,<1'"
        ) from exc

    result = install_specs(PIP_DEPENDENCIES)
    ok = result is True or bool(getattr(result, "ok", False))
    if not ok:
        reason = _safe_install_detail(
            getattr(result, "reason", "") or getattr(result, "stderr", "")
        )
        raise RuntimeError(
            "Unable to install recall-sqlite==0.2.0 through Hermes lazy dependencies: "
            f"{reason}. Manual recovery: pip install recall-sqlite==0.2.0 'httpx>=0.27,<1'"
        )

    importlib.invalidate_caches()
    try:
        importlib.import_module("recall")
    except ImportError as exc:
        raise RuntimeError(
            "Hermes reported a successful install, but recall-sqlite==0.2.0 is still not importable. "
            "Check HERMES_LAZY_INSTALL_TARGET and restart Hermes."
        ) from exc


def _normalize_embed_base_url(value: str) -> str:
    """Normalize an OpenAI-compatible base or endpoint URL."""

    url = str(value or DEFAULT_EMBED_URL).strip().rstrip("/")
    for suffix in ("/v1/embeddings", "/v1/models"):
        if url.lower().endswith(suffix):
            url = url[: -len(suffix)].rstrip("/")
            break
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("embed_url must be an http(s) URL")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("embed_url must not contain credentials; use a protected local proxy")
    return url


def _parse_candidate_multiplier(value: Any) -> int:
    """Parse and clamp candidate expansion without allowing setup to crash."""

    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = DEFAULT_CANDIDATE_MULTIPLIER
    return min(20, max(2, parsed))


def _load_active_provider_config() -> dict[str, Any]:
    """Load this provider's non-secret subsection from active Hermes config."""

    try:
        from hermes_cli.config import load_config

        config = load_config()
    except Exception as exc:
        logger.warning("Unable to load Hermes provider config: %s", exc)
        return {}
    memory = config.get("memory", {}) if isinstance(config, dict) else {}
    provider_config = memory.get(PROVIDER_NAME, {}) if isinstance(memory, dict) else {}
    return dict(provider_config) if isinstance(provider_config, dict) else {}


class RecallMemoryProvider(MemoryProvider):
    """Session-aware Recall provider with curated semantic writes."""

    def __init__(self, config: dict[str, Any] | None = None):
        self._config = dict(config or {})
        self._db_path_config = str(self._config.get("db_path", "")).strip()
        self.db_path = self._db_path_config
        self.embed_url = _normalize_embed_base_url(
            str(self._config.get("embed_url", DEFAULT_EMBED_URL))
        )
        self.embed_model = str(self._config.get("embed_model", DEFAULT_EMBED_MODEL)).strip()
        self.candidate_multiplier = _parse_candidate_multiplier(
            self._config.get("candidate_multiplier", DEFAULT_CANDIDATE_MULTIPLIER)
        )
        self._store: Any = None
        self._session_id = ""
        self._hermes_home = ""
        self._agent_context = "primary"
        self._writes_enabled = False
        self._memory_count = 0

    @property
    def name(self) -> str:
        return "recall"

    @property
    def description(self) -> str:
        return "Local SAG memory: sqlite-vec + FTS5 + keyword RRF with Hot/Warm/Cold tiers"

    def is_available(self) -> bool:
        """Report whether initialization can proceed, without side effects."""

        return _recall_is_importable() or _lazy_installer_is_importable()

    def get_config_schema(self) -> list[dict[str, Any]]:
        return [
            {
                "key": "db_path",
                "description": "Recall DB path (blank = active Hermes profile/recall.db)",
                "default": "",
            },
            {
                "key": "embed_url",
                "description": "OpenAI-compatible embedding base URL",
                "default": DEFAULT_EMBED_URL,
            },
            {
                "key": "embed_model",
                "description": "Embedding model identifier",
                "default": DEFAULT_EMBED_MODEL,
            },
            {
                "key": "candidate_multiplier",
                "description": "Bounded retrieval candidate multiplier (2-20)",
                "default": str(DEFAULT_CANDIDATE_MULTIPLIER),
            },
        ]

    def save_config(self, values: dict[str, Any], hermes_home: str) -> None:
        """Persist non-secret settings into the active Hermes config."""

        del hermes_home  # Active profile resolution belongs to Hermes config helpers.
        from hermes_cli.config import load_config, save_config

        config = load_config()
        if not isinstance(config.get("memory"), dict):
            config["memory"] = {}
        normalized = {
            "db_path": str(values.get("db_path", "")).strip(),
            "embed_url": _normalize_embed_base_url(str(values.get("embed_url", DEFAULT_EMBED_URL))),
            "embed_model": str(values.get("embed_model", DEFAULT_EMBED_MODEL)).strip(),
            "candidate_multiplier": _parse_candidate_multiplier(
                values.get("candidate_multiplier", DEFAULT_CANDIDATE_MULTIPLIER)
            ),
        }
        config["memory"][PROVIDER_NAME] = normalized
        save_config(config)

    def initialize(
        self,
        session_id: str,
        peer_ids: list[str] | None = None,
        hermes_home: str = "",
        agent_context: str = "primary",
        **kwargs: Any,
    ) -> None:
        del peer_ids, kwargs
        self._session_id = session_id
        self._hermes_home = hermes_home or os.path.expanduser("~/.hermes")
        self._agent_context = agent_context or "primary"
        self._writes_enabled = self._agent_context == "primary"

        self.db_path = str(self._resolve_db_path(self._hermes_home))
        self._ensure_runtime_dependencies()
        self._configure_recall_embedding()
        self._store = self._open_store(self.db_path)
        self._memory_count = int(self._store.count())

        logger.info(
            "Recall initialized: db=%s rows=%d context=%s",
            self.db_path,
            self._memory_count,
            self._agent_context,
        )
        if not self._embedding_is_available():
            logger.warning(
                "Embedding endpoint unavailable: base=%s model=%s; Recall will use available non-vector paths",
                self.embed_url,
                self.embed_model,
            )

    def _resolve_db_path(self, hermes_home: str) -> Path:
        if not self._db_path_config:
            return Path(hermes_home) / "recall.db"
        configured = Path(os.path.expandvars(os.path.expanduser(self._db_path_config)))
        return configured if configured.is_absolute() else Path(hermes_home) / configured

    def backup_paths(self) -> list[str]:
        """Declare configured absolute DB state without initializing Recall."""

        if not self._db_path_config:
            return []
        configured = Path(os.path.expandvars(os.path.expanduser(self._db_path_config)))
        if not configured.is_absolute():
            return []
        resolved = configured.resolve(strict=False)
        home_value = os.environ.get("HERMES_HOME", "")
        if not home_value:
            try:
                from hermes_constants import get_hermes_home

                home_value = str(get_hermes_home())
            except (ImportError, TypeError, ValueError):
                home_value = os.path.expanduser("~/.hermes")
        hermes_home = Path(home_value).resolve(strict=False)
        if resolved.is_relative_to(hermes_home):
            return []
        return [str(resolved)]

    def _ensure_runtime_dependencies(self) -> None:
        _ensure_runtime_dependencies()

    def _configure_recall_embedding(self) -> None:
        embed_module = importlib.import_module("recall.embed")
        self._configure_embedding_module(embed_module)

    def _configure_embedding_module(self, embed_module: Any) -> None:
        parsed = urlparse(self.embed_url)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        with _EMBED_CONFIG_LOCK:
            old_route = (
                getattr(embed_module, "EMBED_BASE_URL", None),
                getattr(embed_module, "EMBED_MODEL", None),
            )
            new_route = (self.embed_url, self.embed_model)
            if old_route != new_route:
                cache = getattr(embed_module, "_EMBEDDING_CACHE", None)
                if hasattr(cache, "clear"):
                    cache.clear()
            embed_module.EMBED_BASE_URL = self.embed_url
            embed_module.EMBED_MODEL = self.embed_model
            embed_module.EMBED_PORT = port
            embed_module.EMBED_URL = f"{self.embed_url}/v1/embeddings"

    def _open_store(self, path: str) -> Any:
        from recall.store import SQLiteStore

        db_path = Path(path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return SQLiteStore(str(db_path))

    def _embedding_is_available(self) -> bool:
        try:
            request = Request(f"{self.embed_url}/v1/models")
            with urlopen(request, timeout=2):
                return True
        except Exception:
            return False

    def _embed_text(self, text: str) -> Any:
        return importlib.import_module("recall.embed").embed(text)

    def _new_memory(self, **kwargs: Any) -> Any:
        from recall.store import Memory

        return Memory(**kwargs)

    @staticmethod
    def _stable_memory_id(content: str, session_id: str) -> str:
        identity = f"recall-memory-hermes-v03\0{session_id}\0{content}".encode("utf-8")
        return "rh" + hashlib.sha256(identity).hexdigest()[:22]

    def _candidate_limit(self, k: int) -> int:
        return min(500, max(40, int(k) * self.candidate_multiplier))

    def _retrieve(self, query: str, k: int) -> list[Any]:
        from recall.retrieve import retrieve_relevant

        candidates = retrieve_relevant(
            query,
            self._store,
            k=self._candidate_limit(k),
            tag_filter="semantic",
        )
        return rank_project_candidates(candidates, infer_project(query), k)

    def prefetch(
        self,
        user_message: str = "",
        peer_contexts: list[dict[str, str]] | None = None,
        active_context: str = "primary",
        query: str = "",
        session_id: str = "",
        **kwargs: Any,
    ) -> str:
        del peer_contexts, active_context, session_id, kwargs
        user_message = str(query or user_message).strip()
        if not user_message:
            return ""
        if not self._store:
            return ""
        try:
            memories = self._retrieve(user_message, 5)
            if not memories:
                return ""
            lines = ["## Relevant memories (Recall)"]
            for memory in memories:
                memory_id = str(getattr(memory, "id", ""))[:8]
                content = str(getattr(memory, "content", ""))[:800]
                lines.append(f"- [{memory_id}] {content}")
            return "\n".join(lines)
        except Exception:
            logger.exception("Recall prefetch failed")
            return ""

    def _semantic_rows(self) -> list[Any]:
        if not self._store:
            return []
        try:
            scan_limit = max(MIRROR_SCAN_LIMIT, int(self._store.count()))
        except (AttributeError, TypeError, ValueError):
            scan_limit = MIRROR_SCAN_LIMIT
        return [
            row
            for row in self._store.get_all(limit=scan_limit)
            if getattr(row, "tag", "") == "semantic"
        ]

    def _refresh_count(self) -> None:
        if self._store:
            self._memory_count = int(self._store.count())

    def _add_if_absent(self, content: str, session_id: str) -> bool:
        for row in self._semantic_rows():
            if row.content == content and getattr(row, "session_id", "") == session_id:
                return False
        memory = self._new_memory(
            id=self._stable_memory_id(content, session_id),
            content=content,
            session_id=session_id,
            tag="semantic",
            embedding=self._embed_text(content),
            timestamp=datetime.now(timezone.utc),
        )
        self._store.add(memory)
        self._refresh_count()
        return True

    def _delete_builtin_mirrors(self, target: str, old_text: str) -> int:
        expected_type = f"builtin-{'user' if target == 'user' else 'memory'}"
        expected_card = build_builtin_content(target, old_text)
        expected_body = card_body(expected_card)
        deleted = 0
        for row in list(self._semantic_rows()):
            if extract_type(row.content) != expected_type:
                continue
            if card_body(row.content) != expected_body:
                continue
            if self._store.delete(row.id):
                deleted += 1
        if deleted:
            self._refresh_count()
        return deleted

    def sync_turn(
        self,
        user_content: str,
        assistant_content: str,
        metadata: dict[str, Any] | None = None,
        session_id: str = "",
        messages: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> None:
        del messages, kwargs
        if not self._store or not self._writes_enabled or not should_store_turn(user_content):
            return
        try:
            metadata = metadata if isinstance(metadata, dict) else {}
            effective_session_id = str(metadata.get("session_id", session_id or self._session_id))
            self._add_if_absent(build_semantic_content(user_content, assistant_content), effective_session_id)
        except Exception:
            logger.exception("Recall sync_turn failed")

    def on_memory_write(
        self,
        action: str,
        target: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Mirror committed built-in memory operations with CRUD semantics."""

        if not self._store or not self._writes_enabled:
            return
        action = str(action or "").lower()
        target = str(target or "").lower()
        if action not in {"add", "replace", "remove"} or target not in {"memory", "user"}:
            logger.warning("Ignoring unsupported built-in memory operation: action=%s target=%s", action, target)
            return

        metadata = metadata or {}
        session_id = str(metadata.get("session_id", self._session_id))
        old_text = str(metadata.get("old_text", "")).strip()

        try:
            if action == "add":
                new_content = str(content or "").strip()
                if not new_content:
                    logger.warning("Ignoring add with empty content for target=%s", target)
                    return
                self._add_if_absent(build_builtin_content(target, new_content), session_id)
                return

            if action == "remove":
                old_text = old_text or str(content or "").strip()
                if not old_text:
                    logger.warning("Ignoring remove without old_text for target=%s", target)
                    return
                self._delete_builtin_mirrors(target, old_text)
                return

            # Replace is intentionally add-before-delete. A failed new write
            # preserves the old mirror; a failed old delete leaves a retryable
            # duplicate rather than losing committed memory.
            if not old_text:
                logger.warning("Ignoring replace without old_text for target=%s", target)
                return
            new_content = str(content or "").strip()
            if not new_content:
                logger.warning("Ignoring replace with empty content for target=%s", target)
                return
            old_card = build_builtin_content(target, old_text)
            new_card = build_builtin_content(target, new_content)
            if old_card == new_card:
                return
            self._add_if_absent(new_card, session_id)
            self._delete_builtin_mirrors(target, old_text)
        except Exception:
            logger.exception("Recall on_memory_write failed")

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "memory_recall",
                "description": "Search long-term semantic memory for past decisions, preferences, and project context.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "k": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
                    },
                    "required": ["query"],
                },
            }
        ]

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """Compatibility alias for Hermes <=0.19.0."""

        return self.get_tool_definitions()

    def handle_tool_call(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        **kwargs: Any,
    ) -> str:
        del kwargs
        if tool_name != "memory_recall":
            return f"Unknown memory tool: {tool_name}"
        if not self._store:
            return "Recall is not initialized."
        try:
            query = str(arguments.get("query", "")).strip()
            if not query:
                return "Query must not be empty."
            k = min(20, max(1, int(arguments.get("k", 5))))
            memories = self._retrieve(query, k)
            if not memories:
                return "No relevant memories found."
            lines = [f"Found {len(memories)} relevant memories:"]
            for index, memory in enumerate(memories, 1):
                memory_id = str(getattr(memory, "id", ""))[:8]
                lines.append(f"{index}. [{memory_id}] {str(memory.content)[:1000]}")
            return "\n".join(lines)
        except Exception as exc:
            logger.exception("Recall tool call failed")
            return f"Recall search failed: {type(exc).__name__}: {exc}"

    def system_prompt_section(self) -> str:
        return (
            "## Long-term Memory (Recall)\n"
            "Relevant durable memories are injected automatically. Use `memory_recall` for explicit search. "
            "Ordinary chat is not persisted; only explicit durable decisions, preferences, and corrections are stored."
        )

    def system_prompt_block(self) -> str:
        """Compatibility alias for Hermes <=0.19.0."""

        return self.system_prompt_section()

    def on_session_switch(
        self,
        new_session_id: str,
        *,
        parent_session_id: str = "",
        reset: bool = False,
        rewound: bool = False,
        **kwargs: Any,
    ) -> None:
        del parent_session_id, reset, rewound, kwargs
        if new_session_id:
            self._session_id = new_session_id

    def shutdown(self) -> None:
        self._store = None


def register(ctx: Any) -> None:
    """Hermes plugin entry point."""

    ctx.register_memory_provider(RecallMemoryProvider(_load_active_provider_config()))