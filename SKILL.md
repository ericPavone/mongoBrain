---
name: db-bridge
description: "Persist agent memory, guidelines, and knowledge seeds in MongoDB. Use for: remember/save/store, search knowledge, add guideline, seed/export/import, migrate workspace state, persistent cross-session context. Supports local, remote, Atlas, VPN+TLS."
user-invocable: true
metadata:
  openclaw:
    requires:
      env: [MONGODB_URI]
      bins: [python3]
---

# db-bridge — Persistent Agent Knowledge in MongoDB

## Overview

Three collections complement OpenClaw's native memory (MEMORY.md + daily logs = short-term) with structured, long-term storage:

| Collection | Purpose | Key fields |
|------------|---------|------------|
| `memories` | Facts, preferences, notes, learned knowledge | `content`, `domain`, `category`, `confidence` |
| `guidelines` | SOPs, checklists, best practices per domain/task | `title`, `content`, `domain`, `task`, `priority` |
| `seeds` | Portable knowledge packages (transferable between agents) | `name`, `content`, `domain`, `difficulty`, `dependencies` |

## Connection

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `MONGODB_URI` | `mongodb://localhost:27017` | Connection string |
| `MONGODB_DB` | `openclaw_memory` | Database name |
| `MONGODB_TLS_CA_FILE` | — | CA cert PEM |
| `MONGODB_TLS_CERT_KEY_FILE` | — | Client cert+key PEM |
| `MONGODB_TLS_ALLOW_INVALID_CERTS` | `false` | Allow self-signed |

## Setup

```bash
cd <workspace>/skills/db-bridge
poetry install
poetry run python3 scripts/setup_db.py
```

## Operations Reference

All commands output JSON to stdout. Exit 0 = success, 1 = error.

### Store a memory

```bash
poetry run python3 scripts/memory_ops.py store memory \
  --content "User prefers TypeScript over JavaScript" \
  --category preference \
  --domain programming \
  --tags typescript preferences \
  --confidence 0.95 \
  --source conversation
```

Categories: `fact`, `preference`, `note`, `procedure`, `feedback`.

### Store a guideline

```bash
poetry run python3 scripts/memory_ops.py store guideline \
  --title "Code review checklist" \
  --content "1. Check error handling\n2. Verify tests\n3. Review naming" \
  --domain code-review \
  --task pull-request \
  --priority 8 \
  --tags code-review quality
```

### Store a seed

```bash
poetry run python3 scripts/memory_ops.py store seed \
  --name "python-async-basics" \
  --description "Core async/await patterns in Python" \
  --content "asyncio provides the foundation for async programming..." \
  --domain python \
  --difficulty beginner \
  --tags python async
```

### Search

```bash
# Search memories
poetry run python3 scripts/memory_ops.py search memory --query "typescript" --domain programming

# Search guidelines
poetry run python3 scripts/memory_ops.py search guideline --query "code review" --domain code-review

# Search seeds
poetry run python3 scripts/memory_ops.py search seed --query "async" --domain python
```

### Export seeds

```bash
poetry run python3 scripts/memory_ops.py export-seeds --domain python > python_seeds.json
```

### Import seeds

```bash
poetry run python3 scripts/memory_ops.py import-seeds --file python_seeds.json
```

### Prune expired memories

```bash
poetry run python3 scripts/memory_ops.py prune
```

### Deactivate a guideline

```bash
poetry run python3 scripts/memory_ops.py deactivate --title "Code review checklist"
```

## Migrate OpenClaw Native State

Import existing workspace files, knowledge, templates, projects, and memory into MongoDB.

### Scan (dry run)

```bash
poetry run python3 scripts/memory_ops.py migrate scan --workspace ~/.openclaw/workspace
```

### Migrate everything

```bash
poetry run python3 scripts/memory_ops.py migrate all --workspace ~/.openclaw/workspace
```

### Migrate individual sources

```bash
poetry run python3 scripts/memory_ops.py migrate workspace-files --workspace ~/.openclaw/workspace
poetry run python3 scripts/memory_ops.py migrate knowledge --workspace ~/.openclaw/workspace
poetry run python3 scripts/memory_ops.py migrate templates --workspace ~/.openclaw/workspace
poetry run python3 scripts/memory_ops.py migrate projects --workspace ~/.openclaw/workspace
poetry run python3 scripts/memory_ops.py migrate memory-md --workspace ~/.openclaw/workspace --domain my-agent
poetry run python3 scripts/memory_ops.py migrate daily-logs --workspace ~/.openclaw/workspace --domain my-agent
```

What gets migrated:

| Source | Target | Domain |
|--------|--------|--------|
| SOUL.md, USER.md, IDENTITY.md, TOOLS.md, AGENTS.md, HEARTBEAT.md, BOOTSTRAP.md | seeds | `openclaw-config` |
| knowledge/*.md | seeds | `openclaw-knowledge` |
| templates/*.md | seeds | `openclaw-templates` |
| projects/\<name\>/\*\*/*.md | seeds (1 per project) | `openclaw-projects` |
| MEMORY.md sections | memories | `openclaw-memory` |
| memory/*.md daily logs | memories | `openclaw-daily` |

Migration is idempotent: duplicates are skipped. Safe to re-run.

## Auto-Learn Protocol

Follow these rules to grow the agent's knowledge automatically:

### When to STORE

1. **User says "remember", "save", "don't forget"** → store immediately as `memory` with `source: "conversation"`, `confidence: 0.95`.
2. **After solving a complex problem** → store the solution as a `guideline` (if reusable SOP) or `seed` (if portable knowledge).
3. **User gives corrective feedback** ("no, do it this way") → store as `memory` with `category: feedback`, `confidence: 1.0`. If a conflicting memory exists, update it.
4. **Learning a new fact during conversation** (API behavior, config detail, user preference) → store as `memory` with `category: fact`, `confidence: 0.8`.
5. **After completing a significant task** → evaluate if the approach is worth saving as a `guideline` for future similar tasks.

### When to SEARCH

1. **Before answering any domain-specific question** → search `memories` and `guidelines` for that domain.
2. **When asked "what do you know about X"** → search all three collections.
3. **Before starting a task with established procedures** → search `guidelines` for matching domain+task.
4. **When a topic comes up for the first time in a session** → search `seeds` for foundational knowledge.

### Decision Logic: STORE vs SEARCH

```
User message received
  ├── Contains "remember/save/store/don't forget" → STORE memory
  ├── Asks "what do you know about X" → SEARCH all collections
  ├── Requests a task → SEARCH guidelines for domain+task, then execute
  ├── Provides feedback/correction → STORE memory (feedback category)
  ├── After task completion (significant) → evaluate STORE as guideline
  └── Domain-specific question → SEARCH memories+seeds, then answer
```

### Deduplication

Before storing, the script checks for existing documents with the same `content`+`domain` (memories/guidelines) or `name` (seeds). If a duplicate is found, the operation fails with the existing document in the error output. To update, modify the existing document directly or use a different content/name.

### Integration with Native OpenClaw Memory

- **Short-term**: OpenClaw's MEMORY.md + daily logs (session-memory hook) handle ephemeral, session-scoped context.
- **Long-term**: db-bridge stores structured, searchable, versioned knowledge that persists across sessions and can be transferred between agents.
- **Workflow**: At session start, search db-bridge for relevant context. During session, store significant learnings. MEMORY.md remains the "working memory" scratchpad.

## Seed Store Format

When the user or agent wants to store structured knowledge, follow this format:

```
store memory --content "<the knowledge>" --category <type> --domain <domain> --source conversation
```

For portable knowledge packages:

```
store seed --name "<unique-slug>" --description "<one-liner>" --content "<full knowledge>" --domain <domain> --difficulty <level>
```
