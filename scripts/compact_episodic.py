#!/usr/bin/env python3
"""Archive episodic rows; delete only with explicit --apply and DB backup."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from recall.store import SQLiteStore


def _json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _backup_sqlite(source: Path, target: Path) -> None:
    if target.exists():
        raise FileExistsError(f"refusing to overwrite backup: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as source_db, sqlite3.connect(target) as target_db:
        source_db.backup(target_db)


def compact(
    db_path: Path,
    archive_path: Path,
    *,
    apply: bool = False,
    backup_path: Path | None = None,
) -> dict[str, object]:
    if not db_path.is_file():
        raise FileNotFoundError(f"Recall database does not exist: {db_path}")
    store = SQLiteStore(str(db_path))
    episodic = [memory for memory in store.get_all(limit=1_000_000) if memory.tag == "episodic"]

    if archive_path.exists():
        raise FileExistsError(f"refusing to overwrite archive: {archive_path}")
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with archive_path.open("w", encoding="utf-8") as handle:
        for memory in episodic:
            payload = {
                "id": memory.id,
                "content": memory.content,
                "entities": memory.entities,
                "timestamp": memory.timestamp,
                "embedding": memory.embedding,
                "access_count": memory.access_count,
                "session_id": memory.session_id,
                "tag": memory.tag,
                "tier": memory.tier,
                "last_accessed_at": memory.last_accessed_at,
                "last_demoted_at": memory.last_demoted_at,
            }
            handle.write(json.dumps(payload, ensure_ascii=False, default=_json_default) + "\n")

    archived_lines = sum(1 for _ in archive_path.open("r", encoding="utf-8"))
    if archived_lines != len(episodic):
        raise RuntimeError(f"archive read-back mismatch: expected={len(episodic)} got={archived_lines}")

    deleted = 0
    backup = None
    if apply and episodic:
        backup = backup_path or db_path.with_suffix(
            db_path.suffix + f".bak-v03-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        )
        _backup_sqlite(db_path, backup)
        for memory in episodic:
            if store.delete(memory.id):
                deleted += 1
        verification_store = SQLiteStore(str(db_path))
        remaining_ids = {
            memory.id for memory in verification_store.get_all(limit=1_000_000)
        }
        undeleted = [memory.id for memory in episodic if memory.id in remaining_ids]
        if deleted != len(episodic) or undeleted:
            raise RuntimeError(
                "cleanup read-back mismatch: "
                f"archived={len(episodic)} deleted={deleted} remaining={len(undeleted)}; "
                f"restore from {backup} if needed"
            )

    return {
        "mode": "apply" if apply else "dry-run",
        "found": len(episodic),
        "archived": archived_lines,
        "deleted": deleted,
        "archive": str(archive_path),
        "backup": str(backup) if backup else "",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--apply", action="store_true", help="delete archived episodic rows after DB backup")
    args = parser.parse_args()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    archive = args.archive or args.db.parent / "recall-archives" / f"episodic-archive-{stamp}.jsonl"
    result = compact(args.db, archive, apply=args.apply, backup_path=args.backup)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())