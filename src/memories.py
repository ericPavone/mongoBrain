"""Domain operations for the memories collection."""

import sys
from datetime import datetime, timezone

from connection import get_db, dump, dump_error, text_search_query, TEXT_SCORE_PROJ, TEXT_SCORE_SORT


def store(args):
    col = get_db()["memories"]
    now = datetime.now(timezone.utc)

    existing = col.find_one({"content": args.content, "domain": args.domain})
    if existing:
        dump_error("duplicate", existing=existing)
        sys.exit(1)

    doc = {
        "content": args.content,
        "summary": args.summary or "",
        "domain": args.domain,
        "category": args.category,
        "tags": args.tags or [],
        "confidence": args.confidence,
        "source": args.source,
        "embedding_text": f"{args.content} {args.summary or ''}".strip(),
        "active": True,
        "version": 1,
        "expires_at": datetime.fromisoformat(args.expires_at) if args.expires_at else None,
        "created_at": now,
        "updated_at": now,
    }
    result = col.insert_one(doc)
    doc["_id"] = result.inserted_id
    dump(doc)


def search(args):
    col = get_db()["memories"]
    query = text_search_query(args.query)
    if args.domain:
        query["domain"] = args.domain
    if args.category:
        query["category"] = args.category

    docs = list(
        col.find(query, TEXT_SCORE_PROJ)
        .sort(TEXT_SCORE_SORT)
        .limit(args.limit)
    )
    dump(docs)
