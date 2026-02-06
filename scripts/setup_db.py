#!/usr/bin/env python3
"""Create MongoDB collections, indexes, starter seeds and skills. Idempotent."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from pymongo import TEXT
from pymongo.errors import DuplicateKeyError, OperationFailure

from connection import get_client, get_db

SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"


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
    sd.create_index([("domain", 1)], name="domain")
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


def insert_starter_seeds(db):
    now = datetime.now(timezone.utc)
    col = db["seeds"]

    starters = [
        {
            "name": "mongoBrain-usage",
            "description": "How to use the mongoBrain skill to persist agent knowledge",
            "content": (
                "mongoBrain stores data across 5 collections:\n"
                "1. memories — facts, preferences, notes learned from conversations\n"
                "2. guidelines — SOPs, checklists, best practices per domain/task\n"
                "3. seeds — portable knowledge packages transferable between agents\n"
                "4. agent_config — agent identity sections (soul, tools, identity, etc.)\n"
                "5. skills — self-contained skill bundles with guidelines, seeds, tools, examples\n\n"
                "Use memory_ops.py to store, search, export, import, prune, and deactivate entries."
            ),
            "domain": "openclaw",
            "tags": ["mongoBrain", "memory", "getting-started"],
            "dependencies": [],
            "version": 1,
            "author": "mongoBrain",
            "created_at": now,
            "updated_at": now,
        },
        {
            "name": "skill-creation-wizard",
            "description": "Quick reference for creating mongoBrain skills — points to the full skill-builder skill",
            "content": (
                "To create a new mongoBrain skill, activate the skill-builder:\n\n"
                "  match-skill --trigger 'create skill'\n"
                "  get-skill --name skill-builder\n\n"
                "The skill-builder walks you through 9 steps:\n"
                "1. Briefing & Discovery\n"
                "2. Identity & Metadata (name, triggers, depends_on)\n"
                "3. Prompt Base Composition (role, methodology, behavior)\n"
                "4. Guidelines Authoring (workflow steps with priority + agent delegation)\n"
                "5. Seeds Authoring (embedded knowledge)\n"
                "6. Tools Definition (CLI, MCP, API, manual)\n"
                "7. Examples Creation (usage scenarios)\n"
                "8. References (documentation links)\n"
                "9. Assembly, Validation & Save — assembles the full JSON, validates\n"
                "   uniqueness (name + triggers), saves to skills/<name>.json,\n"
                "   imports into MongoDB via import-skills, verifies with get-skill\n"
                "   and match-skill\n\n"
                "Each step collects information, validates it, and shows a preview.\n"
                "The final step produces a ready-to-use skill in the database."
            ),
            "domain": "openclaw",
            "tags": ["mongoBrain", "skill", "wizard", "creation"],
            "dependencies": ["mongoBrain-usage"],
            "version": 1,
            "author": "mongoBrain",
            "created_at": now,
            "updated_at": now,
        },
    ]

    for seed in starters:
        try:
            col.insert_one(seed)
            print(f"  Starter seed '{seed['name']}' inserted.")
        except DuplicateKeyError:
            print(f"  Starter seed '{seed['name']}' already exists, skipped.")


def insert_starter_skills(db):
    col = db["skills"]
    now = datetime.now(timezone.utc)

    skill_file = SKILLS_DIR / "skill-builder.json"
    if not skill_file.is_file():
        print(f"  WARNING: {skill_file} not found, skipping starter skill.")
        return

    with open(skill_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    skills = data if isinstance(data, list) else [data]
    for s in skills:
        name = s.get("name")
        if not name:
            continue
        s["updated_at"] = now
        s.setdefault("version", 1)
        s.setdefault("prompt_base", "")
        s.setdefault("triggers", [])
        s.setdefault("depends_on", [])
        s.setdefault("guidelines", [])
        s.setdefault("seeds", [])
        s.setdefault("tools", [])
        s.setdefault("examples", [])
        s.setdefault("references", [])
        s.setdefault("active", True)
        created = s.pop("created_at", now)

        r = col.update_one(
            {"name": name},
            {"$set": s, "$setOnInsert": {"created_at": created}},
            upsert=True,
        )
        if r.upserted_id:
            print(f"  Starter skill '{name}' inserted.")
        else:
            print(f"  Starter skill '{name}' already exists, updated.")


def main():
    client = get_client()
    db = get_db()

    print(f"Connecting to {db.name}...")
    client.admin.command("ping")
    print("Connected.")

    ensure_indexes(db)
    print("Indexes ensured for: memories, guidelines, seeds, agent_config, skills.")

    insert_starter_seeds(db)
    insert_starter_skills(db)
    print("Setup complete.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
