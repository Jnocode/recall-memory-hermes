"""Deterministic admission, card formatting, and project-ranking policy."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import Any

MAX_USER_CHARS = 1200
MAX_ASSISTANT_CHARS = 1600
MAX_BUILTIN_CHARS = 2400

_BLOCKED_WRAPPERS = (
    "[delegation complete",
    "[background process",
    "[context compaction",
    "[out-of-band user message",
    "[tool result",
    "[tool output",
    "<tool_result",
    "<tool_output",
    "subagent result",
    "delegation result",
    "reference only]",
)

_DURABLE_MARKERS = (
    "記住",
    "請記得",
    "重大決定",
    "決定：",
    "決定:",
    "結論：",
    "結論:",
    "我的偏好",
    "我偏好",
    "偏好改成",
    "偏好：",
    "偏好:",
    "以後都",
    "從現在起",
    "固定使用",
    "不要再",
    "完成標準",
    "改成",
    "禁止：",
    "禁止:",
    "remember this",
    "remember that",
    "my preference",
    "preference:",
    "from now on",
    "always use",
    "never use",
    "decision:",
)

# Specific projects must precede generic content terms.
_PROJECT_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "hermes-memory",
        (
            "recall-memory",
            "recall memory",
            "recall-sqlite",
            "hermes memory",
            "memory provider",
            "semantic memory",
            "memory_recall",
        ),
    ),
    ("podcast", ("podcast", "soundon", "節目", "單集", "ep qa")),
    ("codegaps", ("代碼縫隙", "code gaps", "codegaps", "方格子", "vocus")),
    (
        "spirits-calling",
        ("spirits calling", "spirits-calling", "靈魂召喚", "弱靈魂", "roguelite"),
    ),
    (
        "job-search",
        ("求職", "履歷", "職缺", "面試", "job search", "resume", "cakeresume", "cake resume"),
    ),
    (
        "trading",
        ("tradingview", "交易策略", "量化交易", "股票", "期貨", "選擇權", "多空", "爆倉"),
    ),
    ("vskin", ("vskin", "live2d", "vtube studio", "v皮", "v 皮")),
    ("comfyui", ("comfyui", "wan2", "wan 2", "latent")),
    (
        "social-publishing",
        ("threads", "facebook", "instagram", "社群發布", "社群貼文", "meta graph"),
    ),
)

_PROJECT_RE = re.compile(r"\[PROJECT:([a-z0-9-]+)\]", re.IGNORECASE)
_TYPE_RE = re.compile(r"\[TYPE:([a-z0-9-]+)\]", re.IGNORECASE)


def _bounded(text: str, limit: int) -> str:
    """Normalize a card body and enforce a deterministic character bound."""

    normalized = str(text or "").replace("\x00", "").strip()
    return normalized if len(normalized) <= limit else normalized[:limit].rstrip() + "…"


def is_blocked_wrapper(user_content: str) -> bool:
    """Return true for orchestration/tool wrappers that are not user memory."""

    lowered = str(user_content or "").strip().lower()
    return any(marker in lowered for marker in _BLOCKED_WRAPPERS)


def should_store_turn(user_content: str) -> bool:
    """Admit only explicit, durable user intent after wrapper rejection."""

    text = str(user_content or "").strip()
    if not text or is_blocked_wrapper(text):
        return False
    lowered = text.lower()
    return any(marker in lowered for marker in _DURABLE_MARKERS)


def infer_project(text: str) -> str:
    """Infer one stable project namespace from human text."""

    lowered = str(text or "").lower()
    for project, markers in _PROJECT_MARKERS:
        if any(marker in lowered for marker in markers):
            return project
    return "general"


def extract_project(content: str) -> str | None:
    """Read a card's explicit project namespace, if present."""

    match = _PROJECT_RE.search(str(content or ""))
    return match.group(1).lower() if match else None


def extract_type(content: str) -> str | None:
    """Read a card's explicit type, if present."""

    match = _TYPE_RE.search(str(content or ""))
    return match.group(1).lower() if match else None


def card_body(content: str) -> str:
    """Return card text after the metadata header."""

    text = str(content or "")
    return text.split("\n", 1)[1] if text.startswith("[PROJECT:") and "\n" in text else text


def build_semantic_content(user_content: str, assistant_content: str) -> str:
    """Build a bounded durable decision card with both sides as evidence."""

    project = infer_project(f"{user_content}\n{assistant_content}")
    user = _bounded(user_content, MAX_USER_CHARS)
    assistant = _bounded(assistant_content, MAX_ASSISTANT_CHARS)
    return f"[PROJECT:{project}][TYPE:decision]\n[USER]\n{user}\n[ASSISTANT]\n{assistant}"


def build_builtin_content(target: str, content: str) -> str:
    """Build a typed mirror card for a committed built-in memory entry."""

    normalized_target = "user" if str(target).lower() == "user" else "memory"
    body = _bounded(content, MAX_BUILTIN_CHARS)
    project = infer_project(body)
    return f"[PROJECT:{project}][TYPE:builtin-{normalized_target}]\n{body}"


def project_matches(content: str, project: str) -> bool:
    """Return whether one card belongs to the requested namespace.

    Untagged legacy cards are general-only.  General cards are deliberately not
    reported as exact matches for project queries; ranking adds them as fallback.
    """

    card_project = extract_project(content)
    if project == "general":
        return card_project in (None, "general")
    return card_project == project


def rank_project_candidates(candidates: Iterable[Any], project: str, k: int) -> list[Any]:
    """Rank exact namespace cards before general fallback and drop unrelated cards."""

    limit = max(0, int(k))
    if not limit:
        return []

    exact: list[Any] = []
    general: list[Any] = []
    for candidate in candidates:
        content = str(getattr(candidate, "content", ""))
        card_project = extract_project(content)
        if project == "general":
            if card_project in (None, "general"):
                exact.append(candidate)
        elif card_project == project:
            exact.append(candidate)
        elif card_project == "general":
            general.append(candidate)

    if project == "general":
        return exact[:limit]
    return (exact + general)[:limit]


def project_names() -> Sequence[str]:
    """Expose known namespaces for deterministic diagnostics/tests."""

    return tuple(project for project, _ in _PROJECT_MARKERS) + ("general",)