"""Migrate OpenClaw native state into MongoDB.

Sources migrated:
- Workspace files (SOUL.md, USER.md, IDENTITY.md, TOOLS.md, AGENTS.md, HEARTBEAT.md, BOOTSTRAP.md) → agent_config
- knowledge/ directory (any .md → seeds)
- templates/ directory (any .md → seeds)
- projects/ directory (each project's .md files → seeds, grouped by project)
- MEMORY.md (sections → memories)
- memory/ daily logs (YYYY-MM-DD-slug.md → memories)
"""

import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from connection import get_db, dump


DEFAULT_WORKSPACE = Path.home() / ".openclaw" / "workspace"

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
_DATE_SLUG_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:-(.+))?\.md$")


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _resolve_workspace(args) -> Path:
    if args.workspace:
        ws = Path(args.workspace).expanduser().resolve()
    else:
        ws = DEFAULT_WORKSPACE
    if not ws.is_dir():
        dump({"error": f"workspace not found: {ws}"})
        sys.exit(1)
    return ws


def _insert_memory(col, content: str, category: str, domain: str,
                   tags: list[str], source: str = "import",
                   summary: str = "", confidence: float = 0.8) -> bool:
    content = content.strip()
    if not content or len(content) < 10:
        return False
    if col.find_one({"content": content, "domain": domain}):
        return False

    now = datetime.now(timezone.utc)
    col.insert_one({
        "content": content,
        "summary": summary,
        "domain": domain,
        "category": category,
        "tags": tags,
        "confidence": confidence,
        "source": source,
        "embedding_text": f"{content} {summary}".strip(),
        "active": True,
        "version": 1,
        "expires_at": None,
        "created_at": now,
        "updated_at": now,
    })
    return True


def _insert_seed(col, name: str, description: str, content: str,
                 domain: str, tags: list[str], difficulty: str = "intermediate") -> bool:
    content = content.strip()
    if not content or len(content) < 10:
        return False
    if col.find_one({"name": name}):
        return False

    now = datetime.now(timezone.utc)
    col.insert_one({
        "name": name,
        "description": description,
        "content": content,
        "domain": domain,
        "difficulty": difficulty,
        "tags": tags,
        "dependencies": [],
        "version": 1,
        "author": "migrate",
        "created_at": now,
        "updated_at": now,
    })
    return True


def _parse_sections(text: str) -> list[dict]:
    entries = []
    lines = text.split("\n")
    current_heading = ""
    current_body: list[str] = []

    for line in lines:
        m = _HEADING_RE.match(line)
        if m:
            if current_heading and current_body:
                entries.append({"heading": current_heading, "body": "\n".join(current_body).strip()})
            current_heading = m.group(2).strip()
            current_body = []
        else:
            current_body.append(line)

    if current_heading and current_body:
        entries.append({"heading": current_heading, "body": "\n".join(current_body).strip()})

    if not entries and text.strip():
        entries.append({"heading": "", "body": text.strip()})

    return entries


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


# --------------------------------------------------------------------------
# Workspace files → agent_config
# --------------------------------------------------------------------------

_WORKSPACE_FILES = [
    ("SOUL.md", "Agent personality and behavioral guidelines", "soul"),
    ("USER.md", "User-specific context and preferences", "user"),
    ("IDENTITY.md", "Agent identity, name, branding", "identity"),
    ("TOOLS.md", "Custom tool instructions and usage", "tools"),
    ("AGENTS.md", "Agent definitions, routing rules, personas", "agents"),
    ("HEARTBEAT.md", "Scheduled heartbeat instructions", "heartbeat"),
    ("BOOTSTRAP.md", "Initial workspace setup instructions", "bootstrap"),
    ("BOOT.md", "Executed on gateway startup via boot-md hook", "boot"),
]


def migrate_workspace_files(args):
    ws = _resolve_workspace(args)
    col = get_db()["agent_config"]
    agent_id = getattr(args, "agent_id", "default") or "default"
    now = datetime.now(timezone.utc)
    upserted = updated = skipped = 0

    for filename, _, slug in _WORKSPACE_FILES:
        filepath = ws / filename
        if not filepath.is_file():
            continue
        text = filepath.read_text(encoding="utf-8").strip()
        if not text or len(text) < 10:
            skipped += 1
            continue

        filter_doc = {"type": slug, "agent_id": agent_id}
        update = {
            "$set": {"content": text, "updated_at": now},
            "$setOnInsert": {"type": slug, "agent_id": agent_id, "version": 1, "created_at": now},
        }
        r = col.update_one(filter_doc, update, upsert=True)
        if r.upserted_id:
            upserted += 1
        elif r.modified_count:
            updated += 1
        else:
            skipped += 1

    dump({"upserted": upserted, "updated": updated, "skipped": skipped,
          "source": str(ws), "agent_id": agent_id, "type": "workspace-files"})


# --------------------------------------------------------------------------
# knowledge/ → seeds
# --------------------------------------------------------------------------

def migrate_knowledge(args):
    ws = _resolve_workspace(args)
    knowledge_dir = ws / "knowledge"

    if not knowledge_dir.is_dir():
        dump({"error": f"knowledge/ not found in {ws}"})
        sys.exit(1)

    col = get_db()["seeds"]
    migrated = skipped = 0

    for md_file in sorted(knowledge_dir.glob("*.md")):
        text = md_file.read_text(encoding="utf-8").strip()
        slug = _slugify(md_file.stem)
        name = f"knowledge-{slug}"
        description = f"Knowledge base: {md_file.stem}"

        if _insert_seed(col, name, description, text, "openclaw-knowledge",
                        ["migrated", "knowledge", slug]):
            migrated += 1
        else:
            skipped += 1

    dump({"migrated": migrated, "skipped": skipped, "source": str(knowledge_dir), "type": "knowledge"})


# --------------------------------------------------------------------------
# templates/ → seeds
# --------------------------------------------------------------------------

def migrate_templates(args):
    ws = _resolve_workspace(args)
    templates_dir = ws / "templates"

    if not templates_dir.is_dir():
        dump({"error": f"templates/ not found in {ws}"})
        sys.exit(1)

    col = get_db()["seeds"]
    migrated = skipped = 0

    for md_file in sorted(templates_dir.glob("*.md")):
        text = md_file.read_text(encoding="utf-8").strip()
        slug = _slugify(md_file.stem)
        name = f"template-{slug}"
        description = f"Template: {md_file.stem}"

        if _insert_seed(col, name, description, text, "openclaw-templates",
                        ["migrated", "template", slug]):
            migrated += 1
        else:
            skipped += 1

    dump({"migrated": migrated, "skipped": skipped, "source": str(templates_dir), "type": "templates"})


# --------------------------------------------------------------------------
# projects/ → seeds (one seed per project, all .md files concatenated)
# --------------------------------------------------------------------------

def _build_project_seed(project_dir: Path) -> dict | None:
    md_files = sorted(project_dir.glob("**/*.md"))
    if not md_files:
        return None

    parts = []
    for md in md_files:
        text = md.read_text(encoding="utf-8").strip()
        if text:
            parts.append(f"# {md.relative_to(project_dir)}\n\n{text}")

    if not parts:
        return None

    slug = _slugify(project_dir.name)
    return {
        "name": f"project-{slug}",
        "description": f"Project specs: {project_dir.name} ({len(md_files)} files)",
        "content": "\n\n---\n\n".join(parts),
        "slug": slug,
    }


def migrate_projects(args):
    ws = _resolve_workspace(args)
    projects_dir = ws / "projects"

    if not projects_dir.is_dir():
        dump({"error": f"projects/ not found in {ws}"})
        sys.exit(1)

    col = get_db()["seeds"]
    migrated = skipped = 0

    for project_dir in sorted(projects_dir.iterdir()):
        if not project_dir.is_dir():
            continue
        seed = _build_project_seed(project_dir)
        if not seed:
            continue
        if _insert_seed(col, seed["name"], seed["description"], seed["content"],
                        "openclaw-projects", ["migrated", "project", seed["slug"]]):
            migrated += 1
        else:
            skipped += 1

    dump({"migrated": migrated, "skipped": skipped, "source": str(projects_dir), "type": "projects"})


# --------------------------------------------------------------------------
# MEMORY.md → memories
# --------------------------------------------------------------------------

def migrate_memory_md(args):
    ws = _resolve_workspace(args)
    memory_file = ws / "MEMORY.md"

    if not memory_file.is_file():
        dump({"error": f"MEMORY.md not found in {ws}"})
        sys.exit(1)

    text = memory_file.read_text(encoding="utf-8")
    entries = _parse_sections(text)
    col = get_db()["memories"]
    domain = args.domain or "openclaw-memory"
    migrated = skipped = 0

    for entry in entries:
        if _insert_memory(col, entry["body"], "note", domain,
                          ["migrated", "memory-md"], summary=entry["heading"], confidence=0.9):
            migrated += 1
        else:
            skipped += 1

    dump({"migrated": migrated, "skipped": skipped, "source": str(memory_file), "type": "memory-md"})


# --------------------------------------------------------------------------
# memory/ daily logs → memories
# --------------------------------------------------------------------------

def _parse_log_entries(log_file: Path) -> list[dict]:
    text = log_file.read_text(encoding="utf-8")
    sections = _parse_sections(text)
    date_match = _DATE_SLUG_RE.match(log_file.name)
    date_str = date_match.group(1) if date_match else log_file.stem
    slug = date_match.group(2) if date_match and date_match.group(2) else ""

    entries = []
    for section in sections:
        tags = ["migrated", "daily-log", f"date:{date_str}"]
        if slug:
            tags.append(f"session:{slug}")
        entries.append({
            "content": section["body"],
            "tags": tags,
            "summary": f"[{date_str}] {section['heading']}",
        })
    return entries


def migrate_daily_logs(args):
    ws = _resolve_workspace(args)
    memory_dir = ws / "memory"

    if not memory_dir.is_dir():
        dump({"error": f"memory/ not found in {ws}"})
        sys.exit(1)

    log_files = sorted(memory_dir.glob("*.md"))
    if not log_files:
        dump({"migrated": 0, "skipped": 0, "files": 0, "source": str(memory_dir), "type": "daily-logs"})
        return

    col = get_db()["memories"]
    domain = args.domain or "openclaw-daily"
    migrated = skipped = 0

    for log_file in log_files:
        for entry in _parse_log_entries(log_file):
            if _insert_memory(col, entry["content"], "note", domain, entry["tags"],
                              summary=entry["summary"], confidence=0.75):
                migrated += 1
            else:
                skipped += 1

    dump({"migrated": migrated, "skipped": skipped, "files": len(log_files),
          "source": str(memory_dir), "type": "daily-logs"})


# --------------------------------------------------------------------------
# seed-boot — ensure BOOT.md has the mongoBrain recovery seed
# --------------------------------------------------------------------------

_BOOT_MARKER = "<!-- mongoBrain:seed-boot -->"

_BOOT_SEED = f"""{_BOOT_MARKER}
## mongoBrain — Identity Recovery

All'avvio, carica la configurazione completa dal database:

```bash
poetry run python3 scripts/memory_ops.py get-config --agent-id default
```

Applica ogni sezione (soul, identity, user, tools, agents, heartbeat, bootstrap)
come contesto operativo per questa sessione.

Poi carica l'indice delle skill attive:

```bash
poetry run python3 scripts/memory_ops.py search skill --query "" --active-only
```

Se una sezione non e' presente nel database, ignorala e prosegui.
"""


def seed_boot(args):
    ws = _resolve_workspace(args)
    boot_file = ws / "BOOT.md"

    if boot_file.is_file():
        existing = boot_file.read_text(encoding="utf-8")
        if _BOOT_MARKER in existing:
            dump({"action": "skipped", "reason": "seed already present", "file": str(boot_file)})
            return
        updated = existing.rstrip() + "\n\n" + _BOOT_SEED
        boot_file.write_text(updated, encoding="utf-8")
        dump({"action": "appended", "file": str(boot_file)})
    else:
        boot_file.write_text(f"# Boot\n\n{_BOOT_SEED}", encoding="utf-8")
        dump({"action": "created", "file": str(boot_file)})


# --------------------------------------------------------------------------
# migrate all
# --------------------------------------------------------------------------

def migrate_all(args):
    ws = _resolve_workspace(args)

    print("--- Workspace files → agent_config ---")
    migrate_workspace_files(args)

    if (ws / "knowledge").is_dir():
        print("\n--- knowledge/ → seeds ---")
        migrate_knowledge(args)

    if (ws / "templates").is_dir():
        print("\n--- templates/ → seeds ---")
        migrate_templates(args)

    if (ws / "projects").is_dir():
        print("\n--- projects/ → seeds ---")
        migrate_projects(args)

    if (ws / "MEMORY.md").is_file():
        print("\n--- MEMORY.md → memories ---")
        migrate_memory_md(args)

    memory_dir = ws / "memory"
    if memory_dir.is_dir() and list(memory_dir.glob("*.md")):
        print("\n--- daily logs → memories ---")
        migrate_daily_logs(args)

    print("\n--- seed-boot → BOOT.md ---")
    seed_boot(args)

    print("\n--- Migration complete ---")


# --------------------------------------------------------------------------
# scan (dry run)
# --------------------------------------------------------------------------

def scan(args):
    ws = _resolve_workspace(args)
    report = {"workspace": str(ws), "found": {}}

    ws_found = []
    for filename, description, _ in _WORKSPACE_FILES:
        filepath = ws / filename
        if filepath.is_file():
            ws_found.append({"file": filename, "description": description, "bytes": filepath.stat().st_size})
    if ws_found:
        report["found"]["workspace_files"] = ws_found

    knowledge_dir = ws / "knowledge"
    if knowledge_dir.is_dir():
        files = sorted(f.name for f in knowledge_dir.glob("*.md"))
        if files:
            report["found"]["knowledge"] = files

    templates_dir = ws / "templates"
    if templates_dir.is_dir():
        files = sorted(f.name for f in templates_dir.glob("*.md"))
        if files:
            report["found"]["templates"] = files

    projects_dir = ws / "projects"
    if projects_dir.is_dir():
        projects = []
        for pd in sorted(projects_dir.iterdir()):
            if pd.is_dir():
                md_files = sorted(f.name for f in pd.glob("**/*.md"))
                if md_files:
                    projects.append({"project": pd.name, "files": md_files})
        if projects:
            report["found"]["projects"] = projects

    memory_file = ws / "MEMORY.md"
    if memory_file.is_file():
        entries = _parse_sections(memory_file.read_text(encoding="utf-8"))
        report["found"]["MEMORY.md"] = {
            "sections": len(entries),
            "headings": [e["heading"] for e in entries],
        }

    memory_dir = ws / "memory"
    if memory_dir.is_dir():
        log_files = sorted(memory_dir.glob("*.md"))
        if log_files:
            details = []
            total = 0
            for lf in log_files:
                entries = _parse_sections(lf.read_text(encoding="utf-8"))
                total += len(entries)
                details.append({"file": lf.name, "entries": len(entries)})
            report["found"]["daily_logs"] = {"files": len(log_files), "total_entries": total, "details": details}

    dump(report)
