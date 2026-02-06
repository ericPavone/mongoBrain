#!/usr/bin/env python3
"""Create MongoDB collections, indexes, and optional starter seed. Idempotent."""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pymongo import TEXT
from pymongo.errors import DuplicateKeyError, OperationFailure

from connection import get_client, get_db


def ensure_indexes(db):
    mem = db["memories"]
    mem.create_index([("domain", 1), ("category", 1)], name="domain_category")
    mem.create_index([("tags", 1)], name="tags")
    mem.create_index([("expires_at", 1)], expireAfterSeconds=0, name="ttl_expiry")
    try:
        mem.create_index(
            [("content", TEXT), ("summary", TEXT), ("embedding_text", TEXT)],
            name="text_search",
        )
    except OperationFailure:
        pass

    gl = db["guidelines"]
    gl.create_index(
        [("domain", 1), ("task", 1), ("active", 1)], name="domain_task_active"
    )
    gl.create_index([("priority", 1)], name="priority")
    gl.create_index([("tags", 1)], name="tags")
    try:
        gl.create_index(
            [("title", TEXT), ("content", TEXT)],
            name="text_search",
        )
    except OperationFailure:
        pass

    sd = db["seeds"]
    sd.create_index([("name", 1)], unique=True, name="name_unique")
    sd.create_index([("domain", 1), ("difficulty", 1)], name="domain_difficulty")
    sd.create_index([("tags", 1)], name="tags")
    try:
        sd.create_index(
            [("name", TEXT), ("description", TEXT), ("content", TEXT)],
            name="text_search",
        )
    except OperationFailure:
        pass

    ac = db["agent_config"]
    ac.create_index(
        [("type", 1), ("agent_id", 1)], unique=True, name="type_agent_unique"
    )
    ac.create_index([("agent_id", 1)], name="agent_id")
    try:
        ac.create_index(
            [("type", TEXT), ("content", TEXT)],
            name="text_search",
        )
    except OperationFailure:
        pass

    sk = db["skills"]
    sk.create_index([("name", 1)], unique=True, name="name_unique")
    sk.create_index([("active", 1)], name="active")
    sk.create_index([("triggers", 1)], name="triggers")
    try:
        sk.create_index(
            [("name", TEXT), ("description", TEXT), ("triggers", TEXT)],
            name="text_search",
        )
    except OperationFailure:
        pass


def insert_starter_seed(db):
    now = datetime.now(timezone.utc)
    try:
        db["seeds"].insert_one(
            {
                "name": "mongoBrain-usage",
                "description": "How to use the mongoBrain skill to persist agent knowledge",
                "content": (
                    "mongoBrain stores three types of data:\n"
                    "1. memories — facts, preferences, notes learned from conversations\n"
                    "2. guidelines — SOPs, checklists, best practices per domain/task\n"
                    "3. seeds — portable knowledge packages transferable between agents\n\n"
                    "Use memory_ops.py to store, search, export, import, prune, and deactivate entries."
                ),
                "domain": "openclaw",
                "difficulty": "beginner",
                "tags": ["mongoBrain", "memory", "getting-started"],
                "dependencies": [],
                "version": 1,
                "author": "mongoBrain",
                "created_at": now,
                "updated_at": now,
            }
        )
        print("Starter seed 'mongoBrain-usage' inserted.")
    except DuplicateKeyError:
        print("Starter seed 'mongoBrain-usage' already exists, skipped.")


def main():
    client = get_client()
    db = get_db()

    print(f"Connecting to {db.name}...")
    client.admin.command("ping")
    print("Connected.")

    ensure_indexes(db)
    print("Indexes ensured for: memories, guidelines, seeds, agent_config, skills.")

    insert_starter_seed(db)
    print("Setup complete.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
