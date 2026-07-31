from __future__ import annotations

import importlib
import sys
import types
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

import recall_memory_hermes as plugin


@dataclass
class FakeMemory:
    content: str
    session_id: str = ""
    tag: str = "semantic"
    id: str = ""
    embedding: object = None
    timestamp: object = None


class FakeStore:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.deleted = []

    def add(self, memory):
        if not memory.id:
            memory.id = f"m{len(self.rows) + 1}"
        self.rows.append(memory)
        return memory.id

    def delete(self, memory_id):
        before = len(self.rows)
        self.rows = [row for row in self.rows if row.id != memory_id]
        if len(self.rows) != before:
            self.deleted.append(memory_id)
            return True
        return False

    def get_all(self, limit=1000):
        return self.rows[:limit]

    def count(self):
        return len(self.rows)


def _provider_with_store(rows=None, *, context="primary"):
    provider = plugin.RecallMemoryProvider()
    provider._store = FakeStore(rows)
    provider._memory_count = len(provider._store.rows)
    provider._writes_enabled = context == "primary"
    provider._session_id = "session-1"
    provider._embed_text = lambda text: [0.0, 1.0]
    provider._new_memory = lambda **kwargs: FakeMemory(**kwargs)
    return provider


def test_is_available_is_side_effect_free(monkeypatch, tmp_path):
    provider = plugin.RecallMemoryProvider({"db_path": str(tmp_path / "missing" / "recall.db")})
    called = []
    monkeypatch.setattr(plugin, "_recall_is_importable", lambda: True, raising=False)
    monkeypatch.setattr(provider, "_ensure_runtime_dependencies", lambda: called.append("install"), raising=False)
    assert provider.is_available()
    assert called == []
    assert not (tmp_path / "missing").exists()


def test_dependency_bootstrap_uses_only_pinned_specs(monkeypatch):
    calls = []
    attempts = iter([ModuleNotFoundError("recall"), object()])

    def fake_import(name):
        result = next(attempts)
        if isinstance(result, Exception):
            result.name = "recall"
            raise result
        return result

    lazy = types.ModuleType("tools.lazy_deps")
    lazy.install_specs = lambda specs: calls.append(tuple(specs)) or True
    monkeypatch.setitem(sys.modules, "tools.lazy_deps", lazy)
    monkeypatch.setattr(plugin.importlib, "import_module", fake_import)

    plugin._ensure_runtime_dependencies()
    assert calls == [tuple(plugin.PIP_DEPENDENCIES)]
    assert calls[0] == ("recall-sqlite==0.2.0", "httpx>=0.27,<1")


def test_dependency_bootstrap_does_not_install_when_recall_imports(monkeypatch):
    calls = []
    lazy = types.ModuleType("tools.lazy_deps")
    lazy.install_specs = lambda specs: calls.append(tuple(specs))
    monkeypatch.setitem(sys.modules, "tools.lazy_deps", lazy)
    monkeypatch.setattr(plugin.importlib, "import_module", lambda name: object())

    plugin._ensure_runtime_dependencies()
    assert calls == []


def test_dependency_bootstrap_failure_is_actionable(monkeypatch):
    def missing(name):
        error = ModuleNotFoundError("recall")
        error.name = "recall"
        raise error

    lazy = types.ModuleType("tools.lazy_deps")
    lazy.install_specs = lambda specs: False
    monkeypatch.setitem(sys.modules, "tools.lazy_deps", lazy)
    monkeypatch.setattr(plugin.importlib, "import_module", missing)

    with pytest.raises(RuntimeError, match=r"recall-sqlite==0\.2\.0"):
        plugin._ensure_runtime_dependencies()


def test_dependency_bootstrap_repairs_missing_transitive_dependency(monkeypatch):
    calls = []
    attempts = iter([ModuleNotFoundError("sqlite_vec"), object()])

    def fake_import(name):
        result = next(attempts)
        if isinstance(result, Exception):
            result.name = "sqlite_vec"
            raise result
        return result

    lazy = types.ModuleType("tools.lazy_deps")
    lazy.install_specs = lambda specs: calls.append(tuple(specs)) or True
    monkeypatch.setitem(sys.modules, "tools.lazy_deps", lazy)
    monkeypatch.setattr(plugin.importlib, "import_module", fake_import)

    plugin._ensure_runtime_dependencies()
    assert calls == [tuple(plugin.PIP_DEPENDENCIES)]


def test_dependency_bootstrap_detects_post_install_import_failure(monkeypatch):
    def still_missing(name):
        error = ModuleNotFoundError("recall")
        error.name = "recall"
        raise error

    lazy = types.ModuleType("tools.lazy_deps")
    lazy.install_specs = lambda specs: types.SimpleNamespace(ok=True)
    monkeypatch.setitem(sys.modules, "tools.lazy_deps", lazy)
    monkeypatch.setattr(plugin.importlib, "import_module", still_missing)

    with pytest.raises(RuntimeError, match="still not importable"):
        plugin._ensure_runtime_dependencies()


def test_embedding_configuration_updates_actual_module():
    embed_module = types.SimpleNamespace(
        EMBED_BASE_URL="old",
        EMBED_MODEL="old",
        EMBED_PORT=1,
        EMBED_URL="old",
    )
    provider = plugin.RecallMemoryProvider(
        {"embed_url": "http://127.0.0.1:1234/v1/embeddings/", "embed_model": "model-id"}
    )
    provider._configure_embedding_module(embed_module)
    assert embed_module.EMBED_BASE_URL == "http://127.0.0.1:1234"
    assert embed_module.EMBED_URL == "http://127.0.0.1:1234/v1/embeddings"
    assert embed_module.EMBED_MODEL == "model-id"
    assert embed_module.EMBED_PORT == 1234


def test_embedding_configuration_clears_cache_only_when_route_changes():
    changed = types.SimpleNamespace(
        EMBED_BASE_URL="http://127.0.0.1:1111",
        EMBED_MODEL="old-model",
        EMBED_PORT=1111,
        EMBED_URL="http://127.0.0.1:1111/v1/embeddings",
        _EMBEDDING_CACHE={"same text": [1.0]},
    )
    provider = plugin.RecallMemoryProvider(
        {"embed_url": "http://127.0.0.1:2222", "embed_model": "new-model"}
    )
    provider._configure_embedding_module(changed)
    assert changed._EMBEDDING_CACHE == {}

    unchanged = types.SimpleNamespace(
        EMBED_BASE_URL="http://127.0.0.1:2222",
        EMBED_MODEL="new-model",
        EMBED_PORT=2222,
        EMBED_URL="http://127.0.0.1:2222/v1/embeddings",
        _EMBEDDING_CACHE={"same text": [2.0]},
    )
    provider._configure_embedding_module(unchanged)
    assert unchanged._EMBEDDING_CACHE == {"same text": [2.0]}


def test_embedding_url_rejects_inline_credentials_without_echoing_secret():
    secret_url = "http://token:supersecret@example.invalid"
    with pytest.raises(ValueError) as exc_info:
        plugin.RecallMemoryProvider({"embed_url": secret_url})
    assert "credentials" in str(exc_info.value).lower()
    assert "supersecret" not in str(exc_info.value)


def test_memory_loader_collector_registers_active_hermes_provider_config(monkeypatch):
    config_module = types.ModuleType("hermes_cli.config")
    config_module.load_config = lambda: {
        "memory": {
            "provider": "recall-memory-hermes",
            "recall-memory-hermes": {
                "embed_url": "http://127.0.0.1:4321",
                "embed_model": "configured-model",
            },
        }
    }
    monkeypatch.setitem(sys.modules, "hermes_cli.config", config_module)

    registered = []
    plugin.register(types.SimpleNamespace(register_memory_provider=registered.append))
    assert registered[0].embed_url == "http://127.0.0.1:4321"
    assert registered[0].embed_model == "configured-model"


def test_manifest_routes_provider_away_from_generic_plugin_context():
    manifest = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "plugin.yaml").read_text(encoding="utf-8")
    )
    assert manifest["kind"] == "exclusive"


def test_save_config_persists_provider_subsection(monkeypatch):
    state = {"memory": {"provider": "recall-memory-hermes"}}
    saved = []
    config_module = types.ModuleType("hermes_cli.config")
    config_module.load_config = lambda: state
    config_module.save_config = lambda config: saved.append(config)
    monkeypatch.setitem(sys.modules, "hermes_cli.config", config_module)

    provider = plugin.RecallMemoryProvider()
    provider.save_config(
        {
            "db_path": "profile-recall.db",
            "embed_url": "http://127.0.0.1:1234/v1/embeddings",
            "embed_model": "model-id",
            "candidate_multiplier": "99",
        },
        "unused-home",
    )
    persisted = saved[0]["memory"]["recall-memory-hermes"]
    assert persisted == {
        "db_path": "profile-recall.db",
        "embed_url": "http://127.0.0.1:1234",
        "embed_model": "model-id",
        "candidate_multiplier": 20,
    }


def test_save_config_invalid_multiplier_uses_safe_default(monkeypatch):
    state = {"memory": {}}
    saved = []
    config_module = types.ModuleType("hermes_cli.config")
    config_module.load_config = lambda: state
    config_module.save_config = lambda config: saved.append(config)
    monkeypatch.setitem(sys.modules, "hermes_cli.config", config_module)

    plugin.RecallMemoryProvider().save_config(
        {"candidate_multiplier": "not-a-number"}, "unused-home"
    )
    assert saved[0]["memory"]["recall-memory-hermes"]["candidate_multiplier"] == 8


def test_initialize_resolves_db_from_active_profile(monkeypatch, tmp_path):
    provider = plugin.RecallMemoryProvider()
    fake_store = FakeStore()
    monkeypatch.setattr(provider, "_ensure_runtime_dependencies", lambda: None, raising=False)
    monkeypatch.setattr(provider, "_configure_recall_embedding", lambda: None, raising=False)
    monkeypatch.setattr(provider, "_open_store", lambda path: fake_store, raising=False)
    monkeypatch.setattr(provider, "_embedding_is_available", lambda: True, raising=False)

    provider.initialize("s1", hermes_home=str(tmp_path), agent_context="primary")
    assert Path(provider.db_path) == tmp_path / "recall.db"
    assert provider._store is fake_store


def test_session_switch_updates_fallback_provenance_for_all_write_paths():
    provider = _provider_with_store()
    provider.on_session_switch(
        "session-after-switch",
        parent_session_id="session-1",
        reset=True,
    )
    provider.on_memory_write("add", "memory", "切換後記憶", {})
    provider.sync_turn("重大決定：切換後決策", "已記錄")
    assert {row.session_id for row in provider._store.rows} == {"session-after-switch"}


def test_backup_paths_declares_only_configured_absolute_db(monkeypatch, tmp_path):
    hermes_home = (tmp_path / "profile").resolve()
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    external = (tmp_path / "external" / "recall.db").resolve()
    assert plugin.RecallMemoryProvider({"db_path": str(external)}).backup_paths() == [str(external)]
    assert plugin.RecallMemoryProvider(
        {"db_path": str(hermes_home / "already-backed-up.db")}
    ).backup_paths() == []
    assert plugin.RecallMemoryProvider({"db_path": "relative/recall.db"}).backup_paths() == []
    assert plugin.RecallMemoryProvider().backup_paths() == []


def test_builtin_add_is_idempotent():
    provider = _provider_with_store()
    metadata = {"session_id": "s1"}
    provider.on_memory_write("add", "memory", "Recall 與 prompt 容量分離", metadata)
    provider.on_memory_write("add", "memory", "Recall 與 prompt 容量分離", metadata)
    assert len(provider._store.rows) == 1
    assert "[TYPE:builtin-memory]" in provider._store.rows[0].content


def test_memory_identity_is_stable_across_provider_instances():
    content = "[PROJECT:general][TYPE:builtin-memory]\nstable"
    first = _provider_with_store()
    second = _provider_with_store()
    assert first._stable_memory_id(content, "s1") == second._stable_memory_id(content, "s1")
    assert first._stable_memory_id(content, "s1") != first._stable_memory_id(content, "s2")


def test_builtin_idempotence_scans_beyond_ten_thousand_rows():
    filler = [
        FakeMemory(
            id=f"d{index}",
            content=f"[PROJECT:general][TYPE:decision]\n{index}",
            session_id="other",
        )
        for index in range(10_000)
    ]
    mirror = FakeMemory(
        id="existing",
        content="[PROJECT:general][TYPE:builtin-memory]\nlarge-db-entry",
        session_id="session-1",
    )
    provider = _provider_with_store(filler + [mirror])
    provider.on_memory_write("add", "memory", "large-db-entry", {"session_id": "session-1"})
    assert len(provider._store.rows) == 10_001


def test_builtin_replace_deletes_old_then_adds_new_once():
    provider = _provider_with_store()
    provider.on_memory_write("add", "user", "偏好舊版", {"session_id": "s1"})
    provider.on_memory_write(
        "replace",
        "user",
        "偏好新版",
        {"session_id": "s1", "old_text": "偏好舊版"},
    )
    assert len(provider._store.rows) == 1
    assert provider._store.rows[0].content.endswith("偏好新版")
    assert "偏好舊版" not in provider._store.rows[0].content


def test_builtin_replace_with_empty_content_preserves_old_mirror():
    provider = _provider_with_store()
    provider.on_memory_write("add", "user", "偏好舊版", {"session_id": "s1"})
    provider.on_memory_write(
        "replace",
        "user",
        "",
        {"session_id": "s1", "old_text": "偏好舊版"},
    )
    assert len(provider._store.rows) == 1
    assert provider._store.rows[0].content.endswith("偏好舊版")


def test_builtin_replace_add_failure_preserves_old_mirror(monkeypatch):
    provider = _provider_with_store()
    provider.on_memory_write("add", "user", "偏好舊版", {"session_id": "s1"})
    monkeypatch.setattr(
        provider,
        "_add_if_absent",
        lambda content, session_id: (_ for _ in ()).throw(RuntimeError("write failed")),
    )
    provider.on_memory_write(
        "replace",
        "user",
        "偏好新版",
        {"session_id": "s1", "old_text": "偏好舊版"},
    )
    assert len(provider._store.rows) == 1
    assert provider._store.rows[0].content.endswith("偏好舊版")


def test_builtin_replace_same_content_is_noop():
    provider = _provider_with_store()
    provider.on_memory_write("add", "memory", "相同內容", {"session_id": "s1"})
    provider.on_memory_write(
        "replace",
        "memory",
        "相同內容",
        {"session_id": "s1", "old_text": "相同內容"},
    )
    assert len(provider._store.rows) == 1
    assert provider._store.rows[0].content.endswith("相同內容")
    assert provider._store.deleted == []


def test_builtin_remove_never_adds_tombstone_and_preserves_decision_card():
    decision = FakeMemory(
        id="decision",
        content="[PROJECT:general][TYPE:decision]\n[USER]\n偏好舊版",
        session_id="s1",
    )
    provider = _provider_with_store([decision])
    provider.on_memory_write("add", "user", "偏好舊版", {"session_id": "s1"})
    provider.on_memory_write(
        "remove",
        "user",
        "",
        {"session_id": "s1", "old_text": "偏好舊版"},
    )
    assert provider._store.rows == [decision]


def test_non_primary_context_suppresses_mirror_writes():
    provider = _provider_with_store(context="cron")
    provider.on_memory_write("add", "memory", "不應保存", {"session_id": "s1"})
    assert provider._store.rows == []


def test_root_git_plugin_loads_in_synthetic_package_namespace():
    root = Path(__file__).resolve().parents[1]
    package_name = "_hermes_test_recall_memory"
    spec = importlib.util.spec_from_file_location(
        package_name,
        root / "__init__.py",
        submodule_search_locations=[str(root)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert module.RecallMemoryProvider().name == "recall"


def test_legacy_tool_call_extra_kwargs_are_accepted():
    provider = plugin.RecallMemoryProvider()
    assert "Unknown" in provider.handle_tool_call("not-a-tool", {}, session_id="legacy")


def test_empty_queries_fail_closed_without_retrieval(monkeypatch):
    provider = _provider_with_store()
    monkeypatch.setattr(
        provider,
        "_retrieve",
        lambda query, k: (_ for _ in ()).throw(AssertionError("retrieval must not run")),
    )
    assert provider.prefetch(user_message="   ") == ""
    assert provider.handle_tool_call("memory_recall", {"query": "", "k": 5}) == (
        "Query must not be empty."
    )
