"""Domain operations for the seeds collection."""

import json
import sys
from datetime import datetime, timezone

from pymongo.errors import DuplicateKeyError

from connection import get_db, dump, dump_error, text_search_query, TEXT_SCORE_PROJ, TEXT_SCORE_SORT


def store(args):
    col = get_db()["seeds"]
    now = datetime.now(timezone.utc)

    existing = col.find_one({"name": args.name})
    if existing:
        dump_error("duplicate", existing=existing)
        sys.exit(1)

    doc = {
        "name": args.name,
        "description": args.description,
        "content": args.content,
        "domain": args.domain,
        "tags": args.tags or [],
        "dependencies": args.dependencies or [],
        "version": 1,
        "author": args.author or "",
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
    col = get_db()["seeds"]
    query = text_search_query(args.query)
    if args.domain:
        query["domain"] = args.domain

    docs = list(
        col.find(query, TEXT_SCORE_PROJ)
        .sort(TEXT_SCORE_SORT)
        .limit(args.limit)
    )
    dump(docs)


def export_all(args):
    col = get_db()["seeds"]
    query: dict = {}
    if args.domain:
        query["domain"] = args.domain

    docs = list(col.find(query))
    for d in docs:
        d.pop("_id", None)
        d.pop("created_at", None)
        d.pop("updated_at", None)
    dump(docs)


def import_from_file(args):
    col = get_db()["seeds"]
    now = datetime.now(timezone.utc)

    with open(args.file, "r", encoding="utf-8") as f:
        seed_list = json.load(f)

    results = {"upserted": 0, "updated": 0, "errors": []}
    for s in seed_list:
        name = s.get("name")
        if not name:
            results["errors"].append({"seed": s, "error": "missing name"})
            continue
        s["updated_at"] = now
        s.setdefault("version", 1)
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
