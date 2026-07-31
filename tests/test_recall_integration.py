from __future__ import annotations

import importlib
import threading
from pathlib import Path

from recall_memory_hermes import RecallMemoryProvider


def test_real_recall_v020_store_crud_and_retrieval(monkeypatch, tmp_path):
    provider = RecallMemoryProvider(
        {
            "db_path": "integration.db",
            "embed_url": "http://127.0.0.1:65534",
            "embed_model": "test-model",
        }
    )
    monkeypatch.setattr(provider, "_embedding_is_available", lambda: False)
    provider.initialize("session-real", hermes_home=str(tmp_path), agent_context="primary")
    monkeypatch.setattr(provider, "_embed_text", lambda text: None)

    user = "重大決定：Spirits Calling 採用弱靈魂潛行探索"
    assistant = "已確認核心手感優先"
    provider.sync_turn(user, assistant, {"session_id": "session-real"})
    provider.sync_turn(user, assistant, {"session_id": "session-real"})
    assert provider._store.count() == 1

    provider.on_memory_write("add", "user", "偏好舊版", {"session_id": "session-real"})
    provider.on_memory_write(
        "replace",
        "user",
        "偏好新版",
        {"session_id": "session-real", "old_text": "偏好舊版"},
    )
    assert provider._store.count() == 2
    provider.on_memory_write(
        "remove",
        "user",
        "",
        {"session_id": "session-real", "old_text": "偏好新版"},
    )
    assert provider._store.count() == 1

    retrieve_module = importlib.import_module("recall.retrieve")
    monkeypatch.setattr(retrieve_module, "embed", lambda text: None)
    memories = provider._retrieve("Spirits Calling", 5)
    assert len(memories) == 1
    assert "[PROJECT:spirits-calling]" in memories[0].content
    assert Path(provider.db_path) == tmp_path / "integration.db"


def test_retrieve_calls_recall_v020_public_api(monkeypatch):
    provider = RecallMemoryProvider()
    provider._store = object()
    captured = {}
    candidate = type(
        "Candidate",
        (),
        {"content": "[PROJECT:general][TYPE:decision]\ngeneral", "id": "1"},
    )()
    retrieve_module = importlib.import_module("recall.retrieve")

    def fake_retrieve(query, store, **kwargs):
        captured.update(query=query, store=store, kwargs=kwargs)
        return [candidate]

    monkeypatch.setattr(retrieve_module, "retrieve_relevant", fake_retrieve)
    assert provider._retrieve("ordinary query", 5) == [candidate]
    assert captured["store"] is provider._store
    assert captured["kwargs"] == {"k": 40, "tag_filter": "semantic"}


def test_concurrent_instances_converge_on_one_deterministic_memory(monkeypatch, tmp_path):
    config = {
        "db_path": "concurrent.db",
        "embed_url": "http://127.0.0.1:65534",
        "embed_model": "test-model",
    }
    providers = [RecallMemoryProvider(config), RecallMemoryProvider(config)]
    for provider in providers:
        monkeypatch.setattr(provider, "_embedding_is_available", lambda: False)
        provider.initialize("shared-session", hermes_home=str(tmp_path), agent_context="primary")
        monkeypatch.setattr(provider, "_embed_text", lambda text: None)

    barrier = threading.Barrier(2)
    for provider in providers:
        monkeypatch.setattr(
            provider,
            "_semantic_rows",
            lambda: (barrier.wait(), [])[1],
        )

    errors = []

    def write(provider):
        try:
            provider.on_memory_write(
                "add",
                "memory",
                "跨 instance 唯一記憶",
                {"session_id": "shared-session"},
            )
        except Exception as exc:  # pragma: no cover - assertion evidence below
            errors.append(exc)

    threads = [threading.Thread(target=write, args=(provider,)) for provider in providers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not errors
    assert all(not thread.is_alive() for thread in threads)
    rows = providers[0]._store.get_all(limit=10)
    assert len(rows) == 1
    assert rows[0].id == providers[0]._stable_memory_id(rows[0].content, "shared-session")
