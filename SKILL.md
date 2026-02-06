---
name: mongoBrain
description: "Persist agent memory, guidelines, seeds, config, and skills in MongoDB. Use for: remember/save/store, search knowledge, add guideline, seed/export/import, agent config, skill discovery/loading, migrate workspace state, persistent cross-session context. Supports local, remote, Atlas, VPN+TLS."
user-invocable: true
metadata:
  openclaw:
    requires:
      env: [MONGODB_URI]
      bins: [python3]
---

# mongoBrain — Persistent Agent Knowledge in MongoDB

## Overview

Five collections complement OpenClaw's native memory (MEMORY.md + daily logs = short-term) with structured, long-term storage:

| Collection | Purpose | Key fields |
|------------|---------|------------|
| `memories` | Facts, preferences, notes, learned knowledge | `content`, `domain`, `category`, `confidence` |
| `guidelines` | SOPs, checklists, best practices per domain/task | `title`, `content`, `domain`, `task`, `priority` |
| `seeds` | Portable knowledge packages (transferable between agents) | `name`, `content`, `domain`, `difficulty`, `dependencies` |
| `agent_config` | Agent config sections (soul, identity, tools, etc.) — upsert by type+agent_id | `type`, `content`, `agent_id` |
| `skills` | Self-contained skills with embedded guidelines, seeds, tools, examples | `name`, `triggers`, `depends_on`, `guidelines[]`, `seeds[]`, `tools[]` |

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
cd <workspace>/skills/mongoBrain
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

### Store agent config (upsert)

```bash
poetry run python3 scripts/memory_ops.py store config \
  --type soul \
  --content "You are a helpful coding assistant." \
  --agent-id default
```

Types: `soul`, `user`, `identity`, `tools`, `agents`, `heartbeat`, `bootstrap`, `boot`. Overwrites if type+agent_id already exists.

### Store a skill (minimal)

```bash
poetry run python3 scripts/memory_ops.py store skill \
  --name "code-review" \
  --description "Structured code review with checklist" \
  --triggers review "code review" "PR review"
```

For full skills with embedded data, use `import-skills --file`.

### Search

```bash
# Search memories
poetry run python3 scripts/memory_ops.py search memory --query "typescript" --domain programming

# Search guidelines
poetry run python3 scripts/memory_ops.py search guideline --query "code review" --domain code-review

# Search seeds
poetry run python3 scripts/memory_ops.py search seed --query "async" --domain python

# Search config
poetry run python3 scripts/memory_ops.py search config --query "assistant" --agent-id default

# Search skills
poetry run python3 scripts/memory_ops.py search skill --query "review" --active-only
```

### Agent Config

```bash
# Load full agent config
poetry run python3 scripts/memory_ops.py get-config --agent-id default

# Load single section
poetry run python3 scripts/memory_ops.py get-config --type soul

# Export / import
poetry run python3 scripts/memory_ops.py export-config --agent-id default > config.json
poetry run python3 scripts/memory_ops.py import-config --file config.json --agent-id other-agent
```

### Skills

```bash
# Match a skill by trigger keyword
poetry run python3 scripts/memory_ops.py match-skill --trigger "review"

# Load full skill (guidelines, seeds, tools, examples, references)
poetry run python3 scripts/memory_ops.py get-skill --name "code-review"

# Import / export
poetry run python3 scripts/memory_ops.py import-skills --file skill.json
poetry run python3 scripts/memory_ops.py export-skills > all-skills.json

# Activate / deactivate
poetry run python3 scripts/memory_ops.py activate-skill --name "code-review"
poetry run python3 scripts/memory_ops.py deactivate-skill --name "code-review"
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
poetry run python3 scripts/memory_ops.py migrate all --workspace ~/.openclaw/workspace --agent-id default
```

### Migrate individual sources

```bash
poetry run python3 scripts/memory_ops.py migrate workspace-files --workspace ~/.openclaw/workspace --agent-id default
poetry run python3 scripts/memory_ops.py migrate knowledge --workspace ~/.openclaw/workspace
poetry run python3 scripts/memory_ops.py migrate templates --workspace ~/.openclaw/workspace
poetry run python3 scripts/memory_ops.py migrate projects --workspace ~/.openclaw/workspace
poetry run python3 scripts/memory_ops.py migrate memory-md --workspace ~/.openclaw/workspace --domain my-agent
poetry run python3 scripts/memory_ops.py migrate daily-logs --workspace ~/.openclaw/workspace --domain my-agent
```

What gets migrated:

| Source | Target | Key |
|--------|--------|-----|
| SOUL.md, USER.md, IDENTITY.md, TOOLS.md, AGENTS.md, HEARTBEAT.md, BOOTSTRAP.md, BOOT.md | agent_config (upsert type+agent_id) | `--agent-id` |
| knowledge/*.md | seeds | `openclaw-knowledge` |
| templates/*.md | seeds | `openclaw-templates` |
| projects/\<name\>/\*\*/*.md | seeds (1 per project) | `openclaw-projects` |
| MEMORY.md sections | memories | `--domain` |
| memory/*.md daily logs | memories | `--domain` |

Migration is idempotent: workspace files use upsert (update if exists, create if new), seeds and memories skip duplicates. Safe to re-run.

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
2. **When asked "what do you know about X"** → search all collections.
3. **Before starting a task with established procedures** → search `guidelines` for matching domain+task.
4. **When a topic comes up for the first time in a session** → search `seeds` for foundational knowledge.
5. **When the user requests a task that might match a skill** → `match-skill --trigger` to find a matching skill, then `get-skill` to load the full context.

### At Session Start

**Main agent:**

1. `get-config --agent-id default` → load all sections (soul, identity, tools, agents, user, heartbeat, bootstrap, boot).
2. `search skill --active-only` → build a lightweight index of available skills (name, triggers, description) for fast matching during the session.

**Sub-agent** (OpenClaw sub-agents only receive AGENTS.md + TOOLS.md natively):

1. `get-config --agent-id default --type agents` + `get-config --agent-id default --type tools` → load only the relevant sections.
2. Skip skill index unless the sub-agent's task requires skill matching.

### Skill Loading Flow

```
User requests a task (e.g. "do a code review")
  │
  ├── match-skill --trigger "review" → finds "code-review"
  ├── get-skill --name "code-review" → loads full skill with:
  │     guidelines[], seeds[], tools[], examples[], references[]
  ├── Check depends_on → load prerequisite skills if needed
  └── Execute guidelines in priority order, respecting agent delegation
```

### Agent Delegation in Guidelines

Guidelines can include an optional `agent` field that acts as a **capability reference**. It tells the runtime who should handle that step.

Resolution order:

```
guideline.agent = "designer"
  │
  ├── 1. Agent available in runtime? (OpenClaw sub-agent, configured agent type)
  │      → Delegate the step to that agent
  │
  ├── 2. Skill exists in DB with that name? (get-skill --name "designer")
  │      → Load the skill's context (guidelines, seeds, tools) and use it
  │      to execute the step
  │
  └── 3. Neither found?
         → Current agent executes the step directly using the guideline content
```

This means `agent` is a soft reference, not a hard dependency. Skills work regardless of whether the referenced agents/skills are available — they just get more capable when they are.

Example: a "landing-page-creation" skill with `agent: "designer"` on the mockup step will:
- Delegate to a designer agent if one exists in the runtime
- Load a "designer" skill from the DB if one is stored there (bringing its own tools, e.g. Figma MCP)
- Fall back to the current agent doing the mockup step itself using the guideline instructions

### Tool Types

Tools can specify a `type` field to indicate how they should be invoked:

| Type | Default | Invocation | Example |
|------|---------|-----------|---------|
| `cli` | yes | Shell command via Bash | `terraform apply` |
| `mcp` | — | MCP tool call (if server available) | `figma_create_file` |
| `api` | — | HTTP request | `https://api.example.com/check` |
| `manual` | — | Instruction for the user, not executable | "Open Figma and share the link" |

If `type` is absent, it defaults to `cli` (backward compatible). Tools with `type: "mcp"` are only usable if the corresponding MCP server is connected. If not, the agent should skip the tool or suggest a manual alternative.

### Decision Logic: STORE vs SEARCH

```
User message received
  ├── Contains "remember/save/store/don't forget" → STORE memory
  ├── Asks "what do you know about X" → SEARCH all collections
  ├── Requests a task → match-skill first, then SEARCH guidelines for domain+task, then execute
  ├── Provides feedback/correction → STORE memory (feedback category)
  ├── After task completion (significant) → evaluate STORE as guideline
  └── Domain-specific question → SEARCH memories+seeds, then answer
```

### Deduplication

Before storing, the script checks for existing documents with the same `content`+`domain` (memories/guidelines) or `name` (seeds). If a duplicate is found, the operation fails with the existing document in the error output. To update, modify the existing document directly or use a different content/name.

### Integration with Native OpenClaw Memory

- **Short-term**: OpenClaw's MEMORY.md + daily logs (session-memory hook) handle ephemeral, session-scoped context.
- **Long-term**: mongoBrain stores structured, searchable, versioned knowledge that persists across sessions and can be transferred between agents.
- **Workflow**: At session start, search mongoBrain for relevant context. During session, store significant learnings. MEMORY.md remains the "working memory" scratchpad.

## Store Formats

When the user or agent wants to store structured knowledge:

```
store memory --content "<the knowledge>" --category <type> --domain <domain> --source conversation
```

For portable knowledge packages:

```
store seed --name "<unique-slug>" --description "<one-liner>" --content "<full knowledge>" --domain <domain> --difficulty <level>
```

For agent configuration (upsert):

```
store config --type <soul|user|identity|tools|agents|heartbeat|bootstrap|boot> --content "<markdown>" --agent-id default
```

For skills (minimal — use import-skills for full documents):

```
store skill --name "<slug>" --description "<one-liner>" --triggers <keyword1> <keyword2>
```
