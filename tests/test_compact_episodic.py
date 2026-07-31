from __future__ import annotations

from datetime import datetime, timezone

import pytest

from recall.store import Memory, SQLiteStore

from scripts.compact_episodic import compact


def test_compaction_dry_run_then_backup_first_apply(tmp_path):
    db_path = tmp_path / "recall.db"
    dry_archive_path = tmp_path / "episodic-dry.jsonl"
    apply_archive_path = tmp_path / "episodic-apply.jsonl"
    backup_path = tmp_path / "recall.before-cleanup.db"
    store = SQLiteStore(str(db_path))
    store.add(
        Memory(
            content="ordinary chat",
            session_id="s1",
            tag="episodic",
            timestamp=datetime.now(timezone.utc),
        )
    )
    store.add(
        Memory(
            content="[PROJECT:general][TYPE:decision]\nkeep",
            session_id="s1",
            tag="semantic",
            timestamp=datetime.now(timezone.utc),
        )
    )

    dry_run = compact(db_path, dry_archive_path)
    assert dry_run["mode"] == "dry-run"
    assert dry_run["found"] == 1
    assert dry_run["deleted"] == 0
    assert store.count() == 2
    assert len(dry_archive_path.read_text(encoding="utf-8").splitlines()) == 1

    applied = compact(db_path, apply_archive_path, apply=True, backup_path=backup_path)
    assert applied["mode"] == "apply"
    assert applied["deleted"] == 1
    assert backup_path.exists() and backup_path.stat().st_size > 0
    assert SQLiteStore(str(db_path)).count() == 1
    assert SQLiteStore(str(backup_path)).count() == 2


def test_compaction_refuses_missing_database_without_creating_it(tmp_path):
    db_path = tmp_path / "missing.db"
    with pytest.raises(FileNotFoundError):
        compact(db_path, tmp_path / "archive.jsonl")
    assert not db_path.exists()


def test_compaction_partial_delete_fails_closed_with_recovery_artifacts(
    monkeypatch,
    tmp_path,
):
    db_path = tmp_path / "recall.db"
    archive_path = tmp_path / "archive.jsonl"
    backup_path = tmp_path / "backup.db"
    store = SQLiteStore(str(db_path))
    for content in ("episodic one", "episodic two"):
        store.add(
            Memory(
                content=content,
                session_id="s1",
                tag="episodic",
                timestamp=datetime.now(timezone.utc),
            )
        )

    original_delete = SQLiteStore.delete
    calls = 0

    def partial_delete(self, memory_id):
        nonlocal calls
        calls += 1
        if calls == 2:
            return False
        return original_delete(self, memory_id)

    monkeypatch.setattr(SQLiteStore, "delete", partial_delete)
    with pytest.raises(RuntimeError, match="cleanup read-back mismatch"):
        compact(db_path, archive_path, apply=True, backup_path=backup_path)

    assert archive_path.exists()
    assert backup_path.exists()
    assert SQLiteStore(str(backup_path)).count() == 2
    assert SQLiteStore(str(db_path)).count() == 1
