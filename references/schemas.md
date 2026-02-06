# mongoBrain — Schema Reference

## Connection

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MONGODB_URI` | `mongodb://localhost:27017` | Connection string (`mongodb://` or `mongodb+srv://`) |
| `MONGODB_DB` | `openclaw_memory` | Database name |
| `MONGODB_TLS_CA_FILE` | — | CA certificate PEM path |
| `MONGODB_TLS_CERT_KEY_FILE` | — | Client certificate+key PEM path |
| `MONGODB_TLS_ALLOW_INVALID_CERTS` | `false` | Allow self-signed certs |

### Scenarios

- **Local**: default, zero config
- **VPS**: `MONGODB_URI=mongodb://user:pass@vps-ip:27017/dbname`
- **Atlas**: `MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/dbname`
- **VPN+TLS**: URI + `MONGODB_TLS_CA_FILE` + `MONGODB_TLS_CERT_KEY_FILE`
- **Self-signed (dev)**: above + `MONGODB_TLS_ALLOW_INVALID_CERTS=true`

---

## Collection: `memories`

Stores facts, preferences, notes, and learned knowledge.

```json
{
  "_id": "ObjectId",
  "content": "string — the memory text (required)",
  "summary": "string — short summary for quick scan (optional)",
  "domain": "string — knowledge domain, e.g. 'python', 'devops' (default: 'general')",
  "category": "string — one of: fact, preference, note, procedure, feedback (required)",
  "tags": ["string — free-form tags for filtering"],
  "confidence": "float 0.0-1.0 — how reliable this memory is (default: 0.8)",
  "source": "string — origin: 'conversation', 'manual', 'import' (default: 'manual')",
  "embedding_text": "string — text used for text search (auto: content + summary)",
  "active": "bool (default: true)",
  "version": "int — incremented on update (default: 1)",
  "expires_at": "datetime or null — TTL expiration (optional)",
  "created_at": "datetime (auto)",
  "updated_at": "datetime (auto)"
}
```

### Indexes

| Name | Fields | Type | Purpose |
|------|--------|------|---------|
| `domain_category` | `{domain: 1, category: 1}` | compound | Filter by domain+category |
| `tags` | `{tags: 1}` | single | Filter by tag |
| `ttl_expiry` | `{expires_at: 1}` | TTL (`expireAfterSeconds: 0`) | Auto-delete expired docs |
| `text_search` | `{content: "text", summary: "text", embedding_text: "text"}` | text | Full-text search |

### Notes

- `expires_at: null` means no expiration.
- TTL index only deletes documents where `expires_at` is a valid date in the past.
- Deduplication: `content` + `domain` uniqueness enforced at application level (not DB unique index, to allow soft-dedup with error message).

---

## Collection: `guidelines`

Stores SOPs, checklists, best practices per domain/task.

```json
{
  "_id": "ObjectId",
  "title": "string — guideline name (required, unique per domain+task)",
  "content": "string — full guideline text (required)",
  "domain": "string — e.g. 'code-review', 'deployment' (default: 'general')",
  "task": "string — specific task this applies to (default: 'general')",
  "priority": "int 1-10 — higher = more important (default: 5)",
  "tags": ["string"],
  "input_format": "string — expected input description (optional)",
  "output_format": "string — expected output description (optional)",
  "active": "bool (default: true)",
  "version": "int (default: 1)",
  "created_at": "datetime (auto)",
  "updated_at": "datetime (auto)"
}
```

### Indexes

| Name | Fields | Type | Purpose |
|------|--------|------|---------|
| `domain_task_active` | `{domain: 1, task: 1, active: 1}` | compound | Lookup active guidelines |
| `priority` | `{priority: 1}` | single | Sort by importance |
| `tags` | `{tags: 1}` | single | Filter by tag |
| `text_search` | `{title: "text", content: "text"}` | text | Full-text search |

---

## Collection: `seeds`

Portable knowledge packages — transferable between agents.

```json
{
  "_id": "ObjectId",
  "name": "string — unique identifier, e.g. 'aws-lambda-basics' (required, unique)",
  "description": "string — what this seed teaches (required)",
  "content": "string — full knowledge content (required)",
  "domain": "string — e.g. 'aws', 'python' (default: 'general')",
  "difficulty": "string — one of: beginner, intermediate, advanced (default: 'intermediate')",
  "tags": ["string"],
  "dependencies": ["string — names of prerequisite seeds"],
  "version": "int (default: 1)",
  "author": "string (optional)",
  "created_at": "datetime (auto)",
  "updated_at": "datetime (auto)"
}
```

### Indexes

| Name | Fields | Type | Purpose |
|------|--------|------|---------|
| `name_unique` | `{name: 1}` | unique | Enforce unique seed names |
| `domain_difficulty` | `{domain: 1, difficulty: 1}` | compound | Filter by domain+level |
| `tags` | `{tags: 1}` | single | Filter by tag |
| `text_search` | `{name: "text", description: "text", content: "text"}` | text | Full-text search |

### Export/Import Format

Seeds are exported as JSON arrays. Each element matches the schema above minus `_id`, `created_at`, `updated_at` (regenerated on import). `name` is the upsert key.

```json
[
  {
    "name": "aws-lambda-basics",
    "description": "Core concepts of AWS Lambda",
    "content": "Lambda is a serverless compute service...",
    "domain": "aws",
    "difficulty": "beginner",
    "tags": ["serverless", "aws", "lambda"],
    "dependencies": [],
    "version": 1,
    "author": "team"
  }
]
```

---

## Collection: `agent_config`

Agent configuration sections. Each document is one config type (soul, identity, tools, etc.) for a specific agent. Upsert semantics: storing the same `type` + `agent_id` overwrites the previous value.

```json
{
  "_id": "ObjectId",
  "type": "string — one of: soul, user, identity, tools, agents, heartbeat, bootstrap, boot (required)",
  "content": "string — markdown content for this config section (required)",
  "agent_id": "string — agent identifier (default: 'default')",
  "version": "int (default: 1)",
  "created_at": "datetime (auto)",
  "updated_at": "datetime (auto)"
}
```

### Indexes

| Name | Fields | Type | Purpose |
|------|--------|------|---------|
| `type_agent_unique` | `{type: 1, agent_id: 1}` | unique compound | One config per type per agent |
| `agent_id` | `{agent_id: 1}` | single | Load all config for an agent at startup |
| `text_search` | `{type: "text", content: "text"}` | text | Full-text search |

### Notes

- `type` + `agent_id` is the logical primary key. `store config` performs upsert (create or overwrite).
- Workspace file migration (`migrate workspace-files`) now targets this collection instead of `seeds`.

### Export/Import Format

Exported as JSON array. Each element matches the schema above minus `_id`, `created_at`, `updated_at`. `type` + `agent_id` is the upsert key.

```json
[
  {
    "type": "soul",
    "content": "You are a helpful coding assistant...",
    "agent_id": "default",
    "version": 1
  }
]
```

---

## Collection: `skills`

Self-contained skill packages with embedded guidelines, seeds, tools, examples, and references. `name` is the unique key.

```json
{
  "_id": "ObjectId",
  "name": "string — unique skill identifier, e.g. 'code-review' (required, unique)",
  "description": "string — what this skill does (required)",
  "version": "int (default: 1)",
  "triggers": ["string — keywords that activate this skill, e.g. 'review', 'PR review'"],
  "depends_on": ["string — names of prerequisite skills"],
  "guidelines": [
    {
      "title": "string",
      "content": "string",
      "task": "string",
      "priority": "int",
      "agent": "string — optional capability reference (agent type or skill name, see resolution logic below)"
    }
  ],
  "seeds": [
    {
      "name": "string",
      "description": "string",
      "content": "string",
      "difficulty": "string"
    }
  ],
  "tools": [
    {
      "name": "string",
      "type": "string — one of: cli, mcp, api, manual (default: 'cli')",
      "command": "string",
      "description": "string",
      "config": "object — optional type-specific parameters (e.g. MCP server config, API headers)"
    }
  ],
  "examples": [
    {
      "input": "string",
      "output": "string",
      "description": "string"
    }
  ],
  "references": [
    {
      "url": "string",
      "title": "string",
      "description": "string"
    }
  ],
  "active": "bool (default: true)",
  "created_at": "datetime (auto)",
  "updated_at": "datetime (auto)"
}
```

### Indexes

| Name | Fields | Type | Purpose |
|------|--------|------|---------|
| `name_unique` | `{name: 1}` | unique | Enforce unique skill names |
| `active` | `{active: 1}` | single | Filter active skills |
| `triggers` | `{triggers: 1}` | multikey | Fast trigger matching |
| `text_search` | `{name: "text", description: "text", triggers: "text"}` | text | Full-text search |

### Notes

- `store skill` creates a minimal skill (name + description + triggers). Use `import-skills --file` for the full document with nested arrays.
- `match-skill --trigger` queries the `triggers` multikey index to find skills by activation keyword.
- `depends_on` references other skill names; the runtime should load dependencies recursively.
- `guidelines[].agent` is a soft capability reference resolved at runtime: (1) known agent type → delegate, (2) skill name in DB → load skill context, (3) neither → current agent handles step. Absence means current agent.
- `tools[].type` defaults to `cli`. Tools with `type: "mcp"` require the MCP server to be connected; if unavailable, skip or suggest manual alternative. `config` carries type-specific parameters (e.g. `file_key` for Figma MCP).

### Export/Import Format

Skills are exported as JSON arrays (or a single object for import). Each element matches the schema above minus `_id`, `created_at`, `updated_at`. `name` is the upsert key.

```json
[
  {
    "name": "code-review",
    "description": "Structured code review with checklist",
    "version": 1,
    "triggers": ["review", "code review", "PR review"],
    "depends_on": ["git-basics"],
    "guidelines": [
      { "title": "Review Checklist", "content": "1. Check naming...", "task": "review", "priority": 9 }
    ],
    "seeds": [],
    "tools": [
      { "name": "diff", "command": "git diff", "description": "Show changes" }
    ],
    "examples": [
      { "input": "Review this PR", "output": "Starting review...", "description": "Basic trigger" }
    ],
    "references": [],
    "active": true
  }
]
```
