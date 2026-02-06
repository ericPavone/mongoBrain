# db-bridge — Schema Reference

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
