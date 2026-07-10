"""Policy for deciding what is durable memory.

The provider must not turn every conversational turn into long-term memory.
Only explicit decisions, preferences, architecture, goals, and durable project
facts enter the semantic store. Raw chat remains available in Hermes sessions.
"""

from __future__ import annotations

import re

SEMANTIC_MARKERS = (
    "記住", "請記得", "重大", "決定", "規劃", "架構", "目標", "偏好",
    "固定", "以後都", "不要再", "改成", "採用", "取代", "優先", "完成標準",
    "remember", "decision", "architecture", "goal", "preference", "policy",
)

PROJECT_MARKERS = (
    ("代碼縫隙", "codegaps"),
    ("recall", "hermes-memory"),
    ("hermes", "hermes"),
    ("podcast", "podcast"),
    ("Podcast", "podcast"),
    ("YouTube", "codegaps-content"),
    ("內容行銷", "codegaps-content"),
)


def should_store_turn(user_content: str) -> bool:
    """Return True only for turns containing durable-memory intent."""
    text = (user_content or "").strip().lower()
    return bool(text) and any(marker.lower() in text for marker in SEMANTIC_MARKERS)


def infer_project(text: str) -> str:
    """Infer a stable project namespace for content-level isolation."""
    for marker, project in PROJECT_MARKERS:
        if marker.lower() in (text or "").lower():
            return project
    return "general"


def build_semantic_content(user_content: str, assistant_content: str) -> str:
    """Build a bounded, auditable semantic card from both sides of a turn."""
    user = (user_content or "").strip()[:900]
    assistant = (assistant_content or "").strip()[:1800]
    project = infer_project(f"{user}\n{assistant}")
    return f"[PROJECT:{project}][TYPE:decision]\n[USER]\n{user}\n[ASSISTANT]\n{assistant}".strip()


def extract_project(content: str) -> str:
    """Read the project namespace embedded in a semantic card."""
    match = re.search(r"\[PROJECT:([^\]]+)\]", content or "")
    return match.group(1) if match else infer_project(content)


def project_matches(content: str, project: str) -> bool:
    """Allow exact namespace matches; legacy untagged cards are global-only."""
    match = re.search(r"\[PROJECT:([^\]]+)\]", content or "")
    if not match:
        return project == "general"
    return match.group(1) in (project, "general")
