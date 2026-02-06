"""Domain operations for the agent_config collection.

Each document represents one config section (soul, identity, tools, etc.)
for a specific agent. Upsert semantics: storing the same type+agent_id
overwrites the previous value.
"""

import json
import sys
from datetime import datetime, timezone

from connection import get_db, dump, dump_error, text_search_query, TEXT_SCORE_PROJ, TEXT_SCORE_SORT


VALID_TYPES = ("soul", "user", "identity", "tools", "agents", "heartbeat", "bootstrap", "boot")


def store(args):
    col = get_db()["agent_config"]
    now = datetime.now(timezone.utc)
    agent_id = getattr(args, "agent_id", "default") or "default"

    if args.type not in VALID_TYPES:
        dump_error("invalid type", type=args.type, valid=list(VALID_TYPES))
        sys.exit(1)

    filter_doc = {"type": args.type, "agent_id": agent_id}
    update = {
        "$set": {
            "content": args.content,
            "updated_at": now,
        },
        "$setOnInsert": {
            "type": args.type,
            "agent_id": agent_id,
            "version": 1,
            "created_at": now,
        },
    }

    result = col.update_one(filter_doc, update, upsert=True)

    doc = col.find_one(filter_doc)
    if result.upserted_id:
        dump({**doc, "_action": "created"})
    else:
        dump({**doc, "_action": "updated"})


def get_config(args):
    col = get_db()["agent_config"]
    agent_id = getattr(args, "agent_id", "default") or "default"
    query: dict = {"agent_id": agent_id}

    config_type = getattr(args, "type", None)
    if config_type:
        query["type"] = config_type

    docs = list(col.find(query).sort("type", 1))
    if not docs:
        dump_error("no config found", agent_id=agent_id)
        sys.exit(1)
    dump(docs)


def search(args):
    col = get_db()["agent_config"]
    query = text_search_query(args.query)

    agent_id = getattr(args, "agent_id", None)
    if agent_id:
        query["agent_id"] = agent_id

    docs = list(
        col.find(query, TEXT_SCORE_PROJ)
        .sort(TEXT_SCORE_SORT)
        .limit(args.limit)
    )
    dump(docs)


def export_config(args):
    col = get_db()["agent_config"]
    agent_id = getattr(args, "agent_id", "default") or "default"

    docs = list(col.find({"agent_id": agent_id}).sort("type", 1))
    for d in docs:
        d.pop("_id", None)
        d.pop("created_at", None)
        d.pop("updated_at", None)
    dump(docs)


def import_from_file(args):
    col = get_db()["agent_config"]
    now = datetime.now(timezone.utc)
    agent_id = getattr(args, "agent_id", "default") or "default"

    with open(args.file, "r", encoding="utf-8") as f:
        config_list = json.load(f)

    results = {"upserted": 0, "updated": 0, "errors": []}
    for entry in config_list:
        cfg_type = entry.get("type")
        if not cfg_type or cfg_type not in VALID_TYPES:
            results["errors"].append({"entry": entry, "error": f"invalid or missing type (valid: {list(VALID_TYPES)})"})
            continue

        content = entry.get("content", "")
        target_agent = agent_id

        filter_doc = {"type": cfg_type, "agent_id": target_agent}
        update = {
            "$set": {"content": content, "updated_at": now},
            "$setOnInsert": {"type": cfg_type, "agent_id": target_agent, "version": 1, "created_at": now},
        }
        r = col.update_one(filter_doc, update, upsert=True)
        if r.upserted_id:
            results["upserted"] += 1
        elif r.modified_count:
            results["updated"] += 1

    dump(results)
