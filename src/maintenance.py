"""Cross-cutting maintenance operations."""

from datetime import datetime, timezone

from connection import get_db, dump


def prune():
    col = get_db()["memories"]
    now = datetime.now(timezone.utc)
    result = col.delete_many({"expires_at": {"$lt": now, "$ne": None}})
    dump({"deleted": result.deleted_count})
