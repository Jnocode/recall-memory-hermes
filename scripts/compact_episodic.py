#!/usr/bin/env python3
"""Archive and remove raw episodic memories from the primary Recall index.

The raw conversation remains in Hermes session history. Recall becomes a
curated semantic store instead of a transcript warehouse.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from recall.store import SQLiteStore


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--archive", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    store = SQLiteStore(args.db)
    episodic = [m for m in store.get_all(limit=100000) if m.tag == "episodic"]
    archive = Path(args.archive)
    archive.parent.mkdir(parents=True, exist_ok=True)
    with archive.open("w", encoding="utf-8") as f:
        for m in episodic:
            f.write(json.dumps({
                "id": m.id, "content": m.content, "session_id": m.session_id,
                "timestamp": m.timestamp.isoformat(), "tag": m.tag,
            }, ensure_ascii=False) + "\n")

    if not args.apply:
        print(f"DRY_RUN episodic={len(episodic)} archive={archive}")
        return 0

    deleted = sum(1 for m in episodic if store.delete(m.id))
    print(f"APPLIED archived={len(episodic)} deleted={deleted} remaining={store.count()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
