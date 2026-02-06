"""Domain operations for the skills collection.

Each document is a self-contained skill with embedded guidelines, seeds,
tools, examples, and references. Name is the unique key.
"""

import json
import sys
from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError

from connection import get_db, dump, dump_error, text_search_query, TEXT_SCORE_PROJ, TEXT_SCORE_SORT


def store(args):
    col = get_db()["skills"]
    now = datetime.now(timezone.utc)

    existing = col.find_one({"name": args.name})
    if existing:
        dump_error("duplicate", existing=existing)
        sys.exit(1)

    triggers = args.triggers or []
    depends_on = args.depends_on or []

    doc = {
        "name": args.name,
        "description": args.description,
        "version": 1,
        "triggers": triggers,
        "depends_on": depends_on,
        "guidelines": [],
        "seeds": [],
        "tools": [],
        "examples": [],
        "references": [],
        "active": True,
        "created_at": now,
        "updated_at": now,
    }
    try:
        result = col.insert_one(doc)
    except DuplicateKeyError:
        dump_error("duplicate name", name=args.name)
        sys.exit(1)
    doc["_id"] = result.inserted_id
    dump(doc)


def search(args):
    col = get_db()["skills"]
    query = text_search_query(args.query)

    active_only = getattr(args, "active_only", False)
    if active_only:
        query["active"] = True

    docs = list(
        col.find(query, TEXT_SCORE_PROJ)
        .sort(TEXT_SCORE_SORT)
        .limit(args.limit)
    )
    dump(docs)


def get_skill(args):
    col = get_db()["skills"]
    doc = col.find_one({"name": args.name})
    if not doc:
        dump_error("skill not found", name=args.name)
        sys.exit(1)
    dump(doc)


def match_skill(args):
    col = get_db()["skills"]
    docs = list(col.find({"triggers": args.trigger, "active": True}))
    if not docs:
        dump_error("no skill matches trigger", trigger=args.trigger)
        sys.exit(1)
    dump(docs)


def activate(args):
    col = get_db()["skills"]
    now = datetime.now(timezone.utc)
    result = col.update_one({"name": args.name}, {"$set": {"active": True, "updated_at": now}})
    if result.matched_count == 0:
        dump_error("skill not found", name=args.name)
        sys.exit(1)
    dump({"activated": args.name})


def deactivate(args):
    col = get_db()["skills"]
    now = datetime.now(timezone.utc)
    result = col.update_one({"name": args.name}, {"$set": {"active": False, "updated_at": now}})
    if result.matched_count == 0:
        dump_error("skill not found", name=args.name)
        sys.exit(1)
    dump({"deactivated": args.name})


def export_skills(args):
    col = get_db()["skills"]
    query: dict = {}
    name = getattr(args, "name", None)
    if name:
        query["name"] = name

    docs = list(col.find(query))
    for d in docs:
        d.pop("_id", None)
        d.pop("created_at", None)
        d.pop("updated_at", None)
    dump(docs)


def import_from_file(args):
    col = get_db()["skills"]
    now = datetime.now(timezone.utc)

    with open(args.file, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        data = [data]

    results = {"upserted": 0, "updated": 0, "errors": []}
    for s in data:
        name = s.get("name")
        if not name:
            results["errors"].append({"skill": s, "error": "missing name"})
            continue

        s["updated_at"] = now
        s.setdefault("version", 1)
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
            results["upserted"] += 1
        elif r.modified_count:
            results["updated"] += 1

    dump(results)
