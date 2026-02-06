#!/usr/bin/env python3
"""CLI entry point for mongoBrain operations."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import agent_config
import guidelines
import maintenance
import memories
import migrate
import seeds
import skills


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="memory_ops", description="mongoBrain memory operations"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- store -----------------------------------------------------------
    store = sub.add_parser("store", help="Store a document")
    store_sub = store.add_subparsers(dest="type", required=True)

    sm = store_sub.add_parser("memory", help="Store a memory")
    sm.add_argument("--content", required=True)
    sm.add_argument(
        "--category",
        required=True,
        choices=["fact", "preference", "note", "procedure", "feedback"],
    )
    sm.add_argument("--domain", default="general")
    sm.add_argument("--summary", default=None)
    sm.add_argument("--tags", nargs="*", default=None)
    sm.add_argument("--confidence", type=float, default=0.8)
    sm.add_argument(
        "--source", default="manual", choices=["conversation", "manual", "import"]
    )
    sm.add_argument(
        "--expires-at", dest="expires_at", default=None, help="ISO datetime"
    )
    sm.set_defaults(func=memories.store)

    sg = store_sub.add_parser("guideline", help="Store a guideline")
    sg.add_argument("--title", required=True)
    sg.add_argument("--content", required=True)
    sg.add_argument("--domain", default="general")
    sg.add_argument("--task", default="general")
    sg.add_argument("--priority", type=int, default=5)
    sg.add_argument("--tags", nargs="*", default=None)
    sg.add_argument("--input-format", dest="input_format", default=None)
    sg.add_argument("--output-format", dest="output_format", default=None)
    sg.set_defaults(func=guidelines.store)

    ss = store_sub.add_parser("seed", help="Store a seed")
    ss.add_argument("--name", required=True)
    ss.add_argument("--description", required=True)
    ss.add_argument("--content", required=True)
    ss.add_argument("--domain", default="general")
    ss.add_argument(
        "--difficulty",
        default="intermediate",
        choices=["beginner", "intermediate", "advanced"],
    )
    ss.add_argument("--tags", nargs="*", default=None)
    ss.add_argument("--dependencies", nargs="*", default=None)
    ss.add_argument("--author", default=None)
    ss.set_defaults(func=seeds.store)

    sc = store_sub.add_parser("config", help="Store an agent config section (upsert)")
    sc.add_argument("--type", required=True, choices=list(agent_config.VALID_TYPES))
    sc.add_argument("--content", required=True)
    sc.add_argument("--agent-id", dest="agent_id", default="default")
    sc.set_defaults(func=agent_config.store)

    sk = store_sub.add_parser("skill", help="Store a skill (minimal)")
    sk.add_argument("--name", required=True)
    sk.add_argument("--description", required=True)
    sk.add_argument("--triggers", nargs="*", default=None)
    sk.add_argument("--depends-on", dest="depends_on", nargs="*", default=None)
    sk.set_defaults(func=skills.store)

    # --- search ----------------------------------------------------------
    search = sub.add_parser("search", help="Search documents")
    search_sub = search.add_subparsers(dest="type", required=True)

    search_funcs = {
        "memory": memories.search,
        "guideline": guidelines.search,
        "seed": seeds.search,
    }
    search_extras = {
        "memory": ["category"],
        "guideline": ["task"],
        "seed": ["difficulty"],
    }

    for name, func in search_funcs.items():
        sp = search_sub.add_parser(name, help=f"Search {name}")
        sp.add_argument("--query", required=True)
        sp.add_argument("--domain", default=None)
        sp.add_argument("--limit", type=int, default=10)
        for extra in search_extras[name]:
            sp.add_argument(f"--{extra}", default=None)
        sp.set_defaults(func=func)

    src = search_sub.add_parser("config", help="Search agent config")
    src.add_argument("--query", required=True)
    src.add_argument("--agent-id", dest="agent_id", default=None)
    src.add_argument("--limit", type=int, default=10)
    src.set_defaults(func=agent_config.search)

    srk = search_sub.add_parser("skill", help="Search skills")
    srk.add_argument("--query", required=True)
    srk.add_argument(
        "--active-only", dest="active_only", action="store_true", default=False
    )
    srk.add_argument("--limit", type=int, default=10)
    srk.set_defaults(func=skills.search)

    # --- get-config ------------------------------------------------------
    gc = sub.add_parser(
        "get-config", help="Get agent config (all sections or one type)"
    )
    gc.add_argument("--agent-id", dest="agent_id", default="default")
    gc.add_argument("--type", default=None, choices=list(agent_config.VALID_TYPES))
    gc.set_defaults(func=agent_config.get_config)

    # --- export-config ---------------------------------------------------
    ec = sub.add_parser("export-config", help="Export agent config as JSON")
    ec.add_argument("--agent-id", dest="agent_id", default="default")
    ec.set_defaults(func=agent_config.export_config)

    # --- import-config ---------------------------------------------------
    ic = sub.add_parser("import-config", help="Import agent config from JSON file")
    ic.add_argument("--file", required=True, help="Path to JSON file")
    ic.add_argument("--agent-id", dest="agent_id", default="default")
    ic.set_defaults(func=agent_config.import_from_file)

    # --- get-skill -------------------------------------------------------
    gs = sub.add_parser("get-skill", help="Get a skill by name")
    gs.add_argument("--name", required=True)
    gs.set_defaults(func=skills.get_skill)

    # --- match-skill -----------------------------------------------------
    ms = sub.add_parser("match-skill", help="Find skills matching a trigger")
    ms.add_argument("--trigger", required=True)
    ms.set_defaults(func=skills.match_skill)

    # --- export-skills ---------------------------------------------------
    exk = sub.add_parser("export-skills", help="Export skills as JSON")
    exk.add_argument("--name", default=None)
    exk.set_defaults(func=skills.export_skills)

    # --- import-skills ---------------------------------------------------
    imk = sub.add_parser("import-skills", help="Import skills from JSON file")
    imk.add_argument("--file", required=True, help="Path to JSON file")
    imk.set_defaults(func=skills.import_from_file)

    # --- activate-skill --------------------------------------------------
    ask = sub.add_parser("activate-skill", help="Activate a skill")
    ask.add_argument("--name", required=True)
    ask.set_defaults(func=skills.activate)

    # --- deactivate-skill ------------------------------------------------
    dsk = sub.add_parser("deactivate-skill", help="Deactivate a skill")
    dsk.add_argument("--name", required=True)
    dsk.set_defaults(func=skills.deactivate)

    # --- export-seeds ----------------------------------------------------
    es = sub.add_parser("export-seeds", help="Export seeds as JSON")
    es.add_argument("--domain", default=None)
    es.set_defaults(func=seeds.export_all)

    # --- import-seeds ----------------------------------------------------
    imp = sub.add_parser("import-seeds", help="Import seeds from JSON file")
    imp.add_argument("--file", required=True, help="Path to JSON file")
    imp.set_defaults(func=seeds.import_from_file)

    # --- prune -----------------------------------------------------------
    pr = sub.add_parser("prune", help="Delete expired memories")
    pr.set_defaults(func=lambda _: maintenance.prune())

    # --- deactivate ------------------------------------------------------
    da = sub.add_parser("deactivate", help="Deactivate a guideline by title")
    da.add_argument("--title", required=True)
    da.add_argument("--domain", default=None)
    da.set_defaults(func=guidelines.deactivate)

    # --- seed-boot -------------------------------------------------------
    sb = sub.add_parser(
        "seed-boot",
        help="Ensure BOOT.md has the mongoBrain recovery seed",
    )
    sb.add_argument(
        "--workspace",
        default=None,
        help="Path to OpenClaw workspace (default: ~/.openclaw/workspace)",
    )
    sb.set_defaults(func=migrate.seed_boot)

    # --- migrate ---------------------------------------------------------
    mg = sub.add_parser("migrate", help="Migrate OpenClaw native state to MongoDB")
    mg_sub = mg.add_subparsers(dest="type", required=True)

    mg_all = mg_sub.add_parser(
        "all", help="Migrate everything: MEMORY.md + daily logs + workspace files"
    )
    mg_all.add_argument(
        "--workspace",
        default=None,
        help="Path to OpenClaw workspace (default: ~/.openclaw/workspace)",
    )
    mg_all.add_argument(
        "--domain", default=None, help="Override domain for imported entries"
    )
    mg_all.add_argument("--agent-id", dest="agent_id", default="default")
    mg_all.set_defaults(func=migrate.migrate_all)

    mg_mem = mg_sub.add_parser("memory-md", help="Migrate MEMORY.md")
    mg_mem.add_argument("--workspace", default=None)
    mg_mem.add_argument("--domain", default=None)
    mg_mem.set_defaults(func=migrate.migrate_memory_md)

    mg_logs = mg_sub.add_parser("daily-logs", help="Migrate daily log files")
    mg_logs.add_argument("--workspace", default=None)
    mg_logs.add_argument("--domain", default=None)
    mg_logs.set_defaults(func=migrate.migrate_daily_logs)

    mg_ws = mg_sub.add_parser(
        "workspace-files", help="Migrate SOUL.md, TOOLS.md, etc. to agent_config"
    )
    mg_ws.add_argument("--workspace", default=None)
    mg_ws.add_argument("--agent-id", dest="agent_id", default="default")
    mg_ws.set_defaults(func=migrate.migrate_workspace_files)

    mg_know = mg_sub.add_parser(
        "knowledge", help="Migrate knowledge/ directory as seeds"
    )
    mg_know.add_argument("--workspace", default=None)
    mg_know.set_defaults(func=migrate.migrate_knowledge)

    mg_tpl = mg_sub.add_parser(
        "templates", help="Migrate templates/ directory as seeds"
    )
    mg_tpl.add_argument("--workspace", default=None)
    mg_tpl.set_defaults(func=migrate.migrate_templates)

    mg_proj = mg_sub.add_parser(
        "projects", help="Migrate projects/ directories as seeds"
    )
    mg_proj.add_argument("--workspace", default=None)
    mg_proj.set_defaults(func=migrate.migrate_projects)

    mg_scan = mg_sub.add_parser("scan", help="Preview what would be migrated (dry run)")
    mg_scan.add_argument("--workspace", default=None)
    mg_scan.set_defaults(func=migrate.scan)

    return parser


def main():
    parser = _build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(json.dumps({"error": str(e)}, indent=2), file=sys.stderr)
        sys.exit(1)
