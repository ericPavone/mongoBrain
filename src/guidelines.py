"""Domain operations for the guidelines collection."""

import sys
from datetime import datetime, timezone

from connection import get_db, dump, dump_error, text_search_query, TEXT_SCORE_PROJ, TEXT_SCORE_SORT


def store(args):
    col = get_db()["guidelines"]
    now = datetime.now(timezone.utc)

    existing = col.find_one({"content": args.content, "domain": args.domain})
    if existing:
        dump_error("duplicate", existing=existing)
        sys.exit(1)

    doc = {
        "title": args.title,
        "content": args.content,
        "domain": args.domain,
        "task": args.task,
        "priority": args.priority,
        "tags": args.tags or [],
        "input_format": args.input_format or "",
        "output_format": args.output_format or "",
        "active": True,
        "version": 1,
        "created_at": now,
        "updated_at": now,
    }
    result = col.insert_one(doc)
    doc["_id"] = result.inserted_id
    dump(doc)


def search(args):
    col = get_db()["guidelines"]
    query = {**text_search_query(args.query), "active": True}
    if args.domain:
        query["domain"] = args.domain
    if args.task:
        query["task"] = args.task

    docs = list(
        col.find(query, TEXT_SCORE_PROJ)
        .sort(TEXT_SCORE_SORT)
        .limit(args.limit)
    )
    dump(docs)


def deactivate(args):
    col = get_db()["guidelines"]
    now = datetime.now(timezone.utc)
    query: dict = {"title": args.title}
    if args.domain:
        query["domain"] = args.domain

    result = col.update_many(query, {"$set": {"active": False, "updated_at": now}})
    if result.modified_count == 0:
        dump_error("no matching guideline found", title=args.title)
        sys.exit(1)
    dump({"deactivated": result.modified_count, "title": args.title})
