# mongoBrain

Skill OpenClaw che aggiunge memoria persistente strutturata a qualsiasi agente, usando MongoDB come storage.

Complementa il sistema nativo di OpenClaw (MEMORY.md + daily logs = memoria di sessione) con un database interrogabile che sopravvive tra sessioni, agenti e macchine diverse.

## Come funziona

```
                    OpenClaw Agent
                         │
          ┌──────────────┼──────────────┐
          │              │              │
     MEMORY.md      daily logs     mongoBrain
   (scratchpad)   (session-memory)  (MongoDB)
     volatile       per-sessione    persistente
                                    strutturato
                                    portabile
```

L'agente ha 5 tipi di storage nel DB:

| Collection | Cosa contiene | Quando usarla |
|------------|--------------|---------------|
| **memories** | Fatti, preferenze, note, correzioni | L'agente impara qualcosa dalla chat |
| **guidelines** | Procedure, checklist, best practice | L'agente deve seguire regole per un task |
| **seeds** | Pacchetti di conoscenza portabili | Trasferire competenze tra agenti |
| **agent_config** | Sezioni di configurazione dell'agente (soul, identity, tools, ecc.) | Definire lo scheletro e il comportamento dell'agente |
| **skills** | Skill self-contained con guidelines, seeds, tools, examples embedded | L'agente deve scoprire, caricare ed eseguire una competenza completa |

### Flusso tipico in una chat

```
1. Sessione inizia
   └→ Agente principale: carica tutta la config (get-config --agent-id default)
      + indice skill attive (search skill --active-only)
   └→ Sub-agente OpenClaw: carica solo agents + tools
      (get-config --type agents + get-config --type tools)
   └→ Cerca nel DB contesto rilevante (memorie + guidelines + seeds)

2. Utente chiede qualcosa
   └→ L'agente cerca nel DB prima di rispondere

3. Utente dice "fai una code review"
   └→ match-skill --trigger "review" → trova la skill "code-review"
   └→ get-skill --name "code-review" → carica guidelines, seeds, tools, examples
   └→ Esegue usando tutto il contesto della skill

4. Utente dice "ricorda che usiamo Traefik"
   └→ L'agente salva come memory (category: fact, source: conversation)

5. Utente corregge: "no, usiamo Caddy non Traefik"
   └→ L'agente salva la correzione (category: feedback, confidence: 1.0)

6. L'agente risolve un problema complesso
   └→ Salva la soluzione come guideline riutilizzabile

7. Utente chiede "cosa sai del nostro stack?"
   └→ L'agente cerca in tutte le collection e sintetizza

8. Sessione finisce
   └→ L'agente salva una nota riepilogativa di cio' che ha imparato
```

---

## Setup

### Prerequisiti

- Python 3.10+
- [Poetry](https://python-poetry.org/)
- MongoDB accessibile (locale, remoto, Atlas, VPN+TLS)

### Installazione

```bash
cd mongoBrain
poetry install
poetry run python3 scripts/setup_db.py
poetry run python3 scripts/memory_ops.py seed-boot --workspace ~/.openclaw/workspace
```

`setup_db.py` crea le 5 collection, tutti gli indici, 2 starter seeds e la skill `skill-builder` (wizard per creare nuove skill). E' idempotente: puoi eseguirlo quante volte vuoi.

`seed-boot` inietta nel BOOT.md del workspace le istruzioni minimali per recuperare l'identita' dell'agente dal database all'avvio. E' il **seme irriducibile**: l'unica informazione che non puo' stare nel DB perche' serve per sapere che il DB esiste. Idempotente: se il seme e' gia' presente, non fa nulla. Se BOOT.md ha gia' altro contenuto, lo appende.

---

## Connessione MongoDB

Tutto gestito via variabili d'ambiente:

| Variabile | Default | Descrizione |
|-----------|---------|-------------|
| `MONGODB_URI` | `mongodb://localhost:27017` | Connection string |
| `MONGODB_DB` | `openclaw_memory` | Nome database |
| `MONGODB_TLS_CA_FILE` | — | Path al CA certificate PEM |
| `MONGODB_TLS_CERT_KEY_FILE` | — | Path al client cert+key PEM |
| `MONGODB_TLS_ALLOW_INVALID_CERTS` | `false` | `true` per self-signed certs |

### Scenari

**Locale** — zero config, usa i default:

```bash
poetry run python3 scripts/setup_db.py
```

**VPS remota**:

```env
MONGODB_URI=mongodb://myuser:mypass@203.0.113.10:27017/openclaw_memory
```

**Cloud Atlas**:

```env
MONGODB_URI=mongodb+srv://myuser:mypass@cluster0.abc123.mongodb.net/openclaw_memory
```

**VPN + mutual TLS**:

```env
MONGODB_URI=mongodb://10.0.0.5:27017
MONGODB_TLS_CA_FILE=/etc/ssl/mongo/ca.pem
MONGODB_TLS_CERT_KEY_FILE=/etc/ssl/mongo/client.pem
```

**Self-signed (dev/test)** — come sopra piu':

```env
MONGODB_TLS_ALLOW_INVALID_CERTS=true
```

---

## Struttura del progetto

```
mongoBrain/
  SKILL.md                    # Definizione skill OpenClaw + istruzioni per l'agente
  pyproject.toml              # Poetry: dipendenze
  references/
    schemas.md                # Schema completo delle 5 collection + indici
  src/                        # Logica di dominio (vertical slice)
    connection.py             # Connessione MongoDB condivisa + helpers
    memories.py               # Operazioni su memories
    guidelines.py             # Operazioni su guidelines
    seeds.py                  # Operazioni su seeds + export/import
    agent_config.py           # Operazioni su agent_config (upsert per type+agent_id)
    skills.py                 # Operazioni su skills (store, match, activate/deactivate)
    maintenance.py            # Prune memorie scadute
    migrate.py                # Migrazione stato nativo OpenClaw → MongoDB
  scripts/                    # Entry point CLI
    setup_db.py               # Crea collection + indici (idempotente)
    memory_ops.py             # CLI con tutti i comandi
  skills/                     # Skill JSON reali
    skill-builder.json        # Wizard per creare nuove skill (installata dal setup)
  tests/
    docker-compose.yml        # MongoDB locale per test (tmpfs)
    test_all.py               # Suite automatica: 206 test su tutte le collection
    fixtures/                 # Skill JSON di esempio usate solo dai test
      k8s-cluster-setup.json
      landing-page-creation.json
```

---

## Comandi CLI

Tutti i comandi producono JSON su stdout. Exit 0 = successo, exit 1 = errore.

### Store

Salva un documento nel DB.

```bash
# Memoria
poetry run python3 scripts/memory_ops.py store memory \
  --content "Il progetto usa PostgreSQL 16 con pgvector" \
  --category fact \
  --domain infrastructure \
  --tags postgres database \
  --confidence 1.0 \
  --source manual

# Guideline
poetry run python3 scripts/memory_ops.py store guideline \
  --title "PR Review Checklist" \
  --content "1. Error handling\n2. Tests\n3. Security\n4. Naming" \
  --domain code-review \
  --task pull-request \
  --priority 9 \
  --tags code-review checklist

# Seed
poetry run python3 scripts/memory_ops.py store seed \
  --name "python-async-basics" \
  --description "Fondamenti async/await in Python" \
  --content "asyncio e' il modulo standard per async programming..." \
  --domain python \
  --tags python async

# Config agente (upsert: sovrascrive se esiste gia')
poetry run python3 scripts/memory_ops.py store config \
  --type soul \
  --content "You are a helpful coding assistant focused on Python." \
  --agent-id default

# Skill (minimale: name + description + triggers)
poetry run python3 scripts/memory_ops.py store skill \
  --name "code-review" \
  --description "Structured code review con checklist" \
  --triggers review "code review" "PR review"
```

**Deduplicazione**: se esiste gia' un documento con lo stesso `content`+`domain` (memory/guideline) o `name` (seed/skill), il comando fallisce con exit 1 e restituisce il documento esistente.

**Upsert**: `store config` e' l'eccezione — sovrascrive il contenuto se `type`+`agent_id` esistono gia'. E' il comportamento corretto: stai *impostando* la config, non aggiungendo una seconda.

### Search

Ricerca full-text con ranking per rilevanza.

```bash
# Cerca memorie
poetry run python3 scripts/memory_ops.py search memory --query "postgres" --domain infrastructure

# Cerca guidelines (solo quelle attive)
poetry run python3 scripts/memory_ops.py search guideline --query "code review" --task pull-request

# Cerca seeds
poetry run python3 scripts/memory_ops.py search seed --query "async python"

# Cerca config agente
poetry run python3 scripts/memory_ops.py search config --query "coding assistant" --agent-id default

# Cerca skills
poetry run python3 scripts/memory_ops.py search skill --query "review" --active-only

# Limita risultati
poetry run python3 scripts/memory_ops.py search memory --query "deploy" --limit 5
```

### Agent Config

```bash
# Carica tutta la config di un agente
poetry run python3 scripts/memory_ops.py get-config --agent-id default

# Carica solo una sezione
poetry run python3 scripts/memory_ops.py get-config --type soul

# Esporta config
poetry run python3 scripts/memory_ops.py export-config --agent-id default > config.json

# Importa config (--agent-id sovrascrive l'agent_id nel file)
poetry run python3 scripts/memory_ops.py import-config --file config.json --agent-id new-agent
```

### Skills

```bash
# Cerca una skill per trigger
poetry run python3 scripts/memory_ops.py match-skill --trigger "review"

# Carica una skill completa (con guidelines, seeds, tools, examples, references)
poetry run python3 scripts/memory_ops.py get-skill --name "code-review"

# Importa una skill completa da file JSON
poetry run python3 scripts/memory_ops.py import-skills --file my-skill.json

# Esporta skills
poetry run python3 scripts/memory_ops.py export-skills > all-skills.json
poetry run python3 scripts/memory_ops.py export-skills --name "code-review" > one-skill.json

# Attiva/disattiva
poetry run python3 scripts/memory_ops.py deactivate-skill --name "code-review"
poetry run python3 scripts/memory_ops.py activate-skill --name "code-review"
```

### Export/Import seeds

```bash
# Esporta tutti i seeds di un dominio
poetry run python3 scripts/memory_ops.py export-seeds --domain python > python-seeds.json

# Esporta tutto
poetry run python3 scripts/memory_ops.py export-seeds > all-seeds.json

# Importa (upsert: aggiorna se esiste, crea se nuovo)
poetry run python3 scripts/memory_ops.py import-seeds --file python-seeds.json
```

### Prune

Cancella memorie con `expires_at` nel passato (backup manuale per il TTL index di MongoDB).

```bash
poetry run python3 scripts/memory_ops.py prune
```

### Deactivate

Disattiva una guideline senza cancellarla (`active: false`).

```bash
poetry run python3 scripts/memory_ops.py deactivate --title "PR Review Checklist"
```

### Seed-Boot

Inietta nel BOOT.md del workspace il seme irriducibile per il recovery dell'identita' dal DB. Idempotente.

```bash
poetry run python3 scripts/memory_ops.py seed-boot --workspace ~/.openclaw/workspace
```

---

## Campi delle collection

### Memory

| Campo | Tipo | Richiesto | Default | Descrizione |
|-------|------|-----------|---------|-------------|
| `content` | string | si | — | Il testo della memoria |
| `category` | string | si | — | `fact`, `preference`, `note`, `procedure`, `feedback` |
| `domain` | string | no | `general` | Dominio di conoscenza |
| `summary` | string | no | `""` | Riassunto breve |
| `tags` | string[] | no | `[]` | Tag per filtering |
| `confidence` | float | no | `0.8` | 0.0-1.0, affidabilita' |
| `source` | string | no | `manual` | `conversation`, `manual`, `import` |
| `expires_at` | datetime | no | `null` | ISO datetime per auto-cancellazione |

### Guideline

| Campo | Tipo | Richiesto | Default | Descrizione |
|-------|------|-----------|---------|-------------|
| `title` | string | si | — | Nome della guideline |
| `content` | string | si | — | Testo completo |
| `domain` | string | no | `general` | Dominio |
| `task` | string | no | `general` | Task specifico |
| `priority` | int | no | `5` | 1-10, importanza |
| `tags` | string[] | no | `[]` | Tag |
| `input_format` | string | no | `""` | Cosa riceve in input |
| `output_format` | string | no | `""` | Cosa produce in output |

### Seed

| Campo | Tipo | Richiesto | Default | Descrizione |
|-------|------|-----------|---------|-------------|
| `name` | string | si | — | Slug unico (chiave di upsert) |
| `description` | string | si | — | Descrizione breve |
| `content` | string | si | — | Contenuto della conoscenza |
| `domain` | string | no | `general` | Dominio |
| `tags` | string[] | no | `[]` | Tag |
| `dependencies` | string[] | no | `[]` | Nomi di seeds prerequisiti |
| `author` | string | no | `""` | Autore |

### Agent Config

| Campo | Tipo | Richiesto | Default | Descrizione |
|-------|------|-----------|---------|-------------|
| `type` | string | si | — | `soul`, `user`, `identity`, `tools`, `agents`, `heartbeat`, `bootstrap`, `boot` |
| `content` | string | si | — | Contenuto markdown della sezione |
| `agent_id` | string | no | `default` | Identificativo dell'agente |

Semantica upsert: `type`+`agent_id` e' la chiave logica. `store config` sovrascrive se esiste gia'.

### Skill

| Campo | Tipo | Richiesto | Default | Descrizione |
|-------|------|-----------|---------|-------------|
| `name` | string | si | — | Slug unico della skill (chiave di upsert) |
| `description` | string | si | — | Descrizione breve |
| `prompt_base` | string | no | `""` | Prompt comportamentale: ruolo, metodologia, vincoli dell'agente |
| `triggers` | string[] | no | `[]` | Keywords che attivano la skill |
| `depends_on` | string[] | no | `[]` | Nomi di skill prerequisite |
| `guidelines` | object[] | no | `[]` | Guidelines embedded (title, content, task, priority, domain, tags, agent) |
| `seeds` | object[] | no | `[]` | Seeds embedded (name, description, content, domain, tags, dependencies, author, version) |
| `tools` | object[] | no | `[]` | Tools embedded (name, command, description, type, config) |
| `examples` | object[] | no | `[]` | Esempi embedded (input, output, description) |
| `references` | object[] | no | `[]` | Riferimenti embedded (url, title, description) |
| `active` | bool | no | `true` | Attiva/disattiva senza cancellare |

`store skill` crea una skill minimale (name + description + triggers + prompt_base). Per il documento completo con nested arrays, usare `import-skills --file`.

Schema unificato: guidelines e seeds embedded in una skill accettano tutti i campi canonici delle rispettive collection standalone. Un seed embedded ha lo stesso schema di un seed nella collection `seeds` (meno `_id`, `created_at`, `updated_at`). Questo permette round-trip senza perdita di informazione.

Tutti i documenti hanno anche `version`, `active` (memory/guideline/skill), `created_at`, `updated_at` generati automaticamente.

---

## Creare un pacchetto seeds (skill pack)

Un skill pack e' un file JSON con un array di seeds. Rappresenta un "corso" o un "modulo di competenza" che puoi importare su qualsiasi agente.

### Struttura

```json
[
  {
    "name": "slug-unico-del-seed",
    "description": "Cosa insegna, in una riga",
    "content": "Contenuto completo. Puo' essere lungo.\nUsa \\n per i newline.",
    "domain": "nome-dominio",
    "tags": ["tag1", "tag2"],
    "dependencies": [],
    "author": "tuo-nome",
    "version": 1
  }
]
```

### Esempio passo-passo: creare un pack "kubernetes-basics"

1. Crea il file `packs/kubernetes.json`:

```json
[
  {
    "name": "k8s-core-concepts",
    "description": "Pod, Deployment, Service, Namespace: i mattoni di Kubernetes",
    "content": "Kubernetes orchestra container su un cluster di nodi.\n\nConcetti fondamentali:\n\n- Pod: unita' minima di deployment, 1+ container che condividono network e storage\n- Deployment: gestisce repliche di Pod, rolling update, rollback\n- Service: endpoint stabile per accedere ai Pod (ClusterIP, NodePort, LoadBalancer)\n- Namespace: isolamento logico delle risorse nel cluster\n- ConfigMap/Secret: configurazione esternalizzata\n- PersistentVolume: storage che sopravvive al Pod\n\nComandi essenziali:\n- kubectl get pods/deploy/svc -n <namespace>\n- kubectl describe pod <name>\n- kubectl logs <pod> -f\n- kubectl apply -f manifest.yaml\n- kubectl rollout status deployment/<name>",
    "domain": "kubernetes",
    "tags": ["k8s", "containers", "orchestration"],
    "dependencies": [],
    "author": "team",
    "version": 1
  },
  {
    "name": "k8s-networking",
    "description": "Ingress, NetworkPolicy, DNS interno di Kubernetes",
    "content": "Networking in Kubernetes:\n\n1. Ogni Pod ha un IP unico nel cluster\n2. I Service forniscono DNS: <service>.<namespace>.svc.cluster.local\n3. Ingress: routing HTTP/HTTPS dall'esterno ai Service\n   - Richiede un Ingress Controller (nginx, traefik, istio)\n   - Supporta TLS termination, path-based e host-based routing\n4. NetworkPolicy: firewall L3/L4 tra Pod\n   - Default: tutto aperto\n   - Deny-all + whitelist e' la best practice\n5. Service Mesh (opzionale): mTLS, observability, traffic management",
    "domain": "kubernetes",
    "tags": ["k8s", "networking", "ingress"],
    "dependencies": ["k8s-core-concepts"],
    "author": "team",
    "version": 1
  },
  {
    "name": "k8s-troubleshooting",
    "description": "Debug di Pod che non partono, CrashLoopBackOff, risorse insufficienti",
    "content": "Troubleshooting Kubernetes:\n\nPod in Pending:\n- kubectl describe pod → controlla Events\n- Cause comuni: risorse insufficienti, PVC non bound, node selector senza match\n\nPod in CrashLoopBackOff:\n- kubectl logs <pod> --previous → log del container crashato\n- Cause: errore applicativo, config mancante, probe che fallisce\n\nPod in ImagePullBackOff:\n- Immagine non esiste o registry non raggiungibile\n- Controllare imagePullSecrets\n\nService non raggiungibile:\n- kubectl get endpoints <svc> → se vuoto, selector non matcha i Pod\n- Controllare labels Pod vs selector Service\n\nRisorse:\n- kubectl top pods/nodes → uso CPU/memory\n- kubectl describe node → Allocatable vs Allocated",
    "domain": "kubernetes",
    "tags": ["k8s", "debug", "troubleshooting"],
    "dependencies": ["k8s-core-concepts"],
    "author": "team",
    "version": 1
  }
]
```

1. Importa:

```bash
poetry run python3 scripts/memory_ops.py import-seeds --file packs/kubernetes.json
```

Output:

```json
{ "upserted": 3, "updated": 0, "errors": [] }
```

1. Verifica:

```bash
poetry run python3 scripts/memory_ops.py search seed --query "kubernetes pod" --domain kubernetes
```

### Convenzioni per organizzare i packs

- Un file per dominio: `packs/kubernetes.json`, `packs/aws.json`, `packs/python.json`
- Naming dei seeds: `<dominio>-<topic>`, es. `k8s-core-concepts`, `aws-lambda-basics`
- Usa `dependencies` per creare percorsi: basics → intermediate → advanced
- `tags` servono per il filtering, non per la ricerca (la ricerca usa full-text su `name` + `description` + `content`)

### Template vuoto

```json
[
  {
    "name": "",
    "description": "",
    "content": "",
    "domain": "",
    "tags": [],
    "dependencies": [],
    "author": "",
    "version": 1
  }
]
```

---

## Portabilita': trasferire conoscenza tra agenti

Esporta da agente A:

```bash
poetry run python3 scripts/memory_ops.py export-seeds --domain kubernetes > k8s-seeds.json
```

Importa su agente B (diverso DB, diversa macchina):

```bash
MONGODB_URI=mongodb://other-host:27017 \
  poetry run python3 scripts/memory_ops.py import-seeds --file k8s-seeds.json
```

L'import usa upsert: se un seed con lo stesso `name` esiste gia', viene aggiornato. Se e' nuovo, viene creato.

---

## Pre-popolare memorie e guidelines

### Memorie: fatti che l'agente deve sapere da subito

```bash
# Singolo fatto
poetry run python3 scripts/memory_ops.py store memory \
  --content "Il progetto usa Next.js 15 con App Router" \
  --category fact \
  --domain stack \
  --confidence 1.0

# Preferenza utente
poetry run python3 scripts/memory_ops.py store memory \
  --content "L'utente preferisce risposte concise con esempi di codice" \
  --category preference \
  --domain communication \
  --confidence 0.95 \
  --source manual
```

**Categorie**:

| Categoria | Quando usarla |
|-----------|--------------|
| `fact` | Dati oggettivi: versioni, stack, configurazione |
| `preference` | Come l'utente vuole lavorare |
| `note` | Osservazioni, appunti contestuali |
| `procedure` | Step operativi, workflow |
| `feedback` | Correzioni dall'utente ("no, si fa cosi'") |

### Guidelines: regole operative per task specifici

```bash
poetry run python3 scripts/memory_ops.py store guideline \
  --title "Commit message format" \
  --content "Conventional commits: type(scope): description\n\nTypes: feat, fix, refactor, docs, test, chore\nScope: modulo o area\nDescrizione: imperativo, minuscolo, senza punto finale\nMax 72 caratteri per la prima riga" \
  --domain git \
  --task commit \
  --priority 9 \
  --tags git conventions
```

Disattivare una guideline (senza cancellarla):

```bash
poetry run python3 scripts/memory_ops.py deactivate --title "Commit message format"
```

---

## Come l'agente usa mongoBrain (Auto-Learn Protocol)

Queste regole sono nel SKILL.md e guidano il comportamento automatico dell'agente.

### Quando l'agente SALVA

| Trigger | Azione | Categoria | Confidence |
|---------|--------|-----------|------------|
| Utente dice "ricorda", "salva", "non dimenticare" | Store immediato | fact/preference | 0.95 |
| Utente corregge l'agente | Store correzione | feedback | 1.0 |
| Agente impara un fatto nuovo | Store | fact | 0.8 |
| Agente risolve un problema complesso | Store soluzione | guideline o seed | — |
| Fine sessione significativa | Store nota riepilogativa | note | 0.85 |

### Quando l'agente CERCA

| Situazione | Cosa cerca | Dove |
|------------|-----------|------|
| Prima di rispondere su un dominio | Contesto rilevante | memories + guidelines |
| "Cosa sai di X?" | Tutto | memories + guidelines + seeds |
| Prima di iniziare un task | Procedure stabilite | guidelines (domain + task) |
| Dominio nuovo in sessione | Conoscenza base | seeds |
| Inizio sessione | Contesto precedente | memories |

### Deduplicazione

Il sistema rifiuta inserimenti duplicati:

- **memories/guidelines**: stesso `content` + `domain` → errore con doc esistente
- **seeds**: stesso `name` → errore con doc esistente

Questo evita che l'agente salvi la stessa informazione piu' volte.

---

## Migrazione dallo stato nativo OpenClaw

Se hai gia' un agente OpenClaw attivo con workspace popolato, puoi importare tutto nel DB con un solo comando. La migrazione legge i file dal workspace e li salva come seeds o memories nel MongoDB.

### Cosa viene migrato

| Sorgente | Destinazione | Chiave |
|----------|-------------|--------|
| `SOUL.md`, `USER.md`, `IDENTITY.md`, `TOOLS.md`, `AGENTS.md`, `HEARTBEAT.md`, `BOOTSTRAP.md`, `BOOT.md` | agent_config (upsert su type+agent_id) | `--agent-id` |
| `knowledge/*.md` | seeds | `openclaw-knowledge` |
| `templates/*.md` | seeds | `openclaw-templates` |
| `projects/<nome>/**/*.md` | seeds (1 seed per progetto, file concatenati) | `openclaw-projects` |
| `MEMORY.md` (sezioni) | memories | `--domain` |
| `memory/*.md` (daily logs) | memories | `--domain` |

### Scan (dry run)

Prima di migrare, controlla cosa verrebbe importato:

```bash
poetry run python3 scripts/memory_ops.py migrate scan --workspace ~/.openclaw/workspace
```

Output di esempio:

```json
{
  "workspace": "/home/claw/.openclaw/workspace",
  "found": {
    "workspace_files": [
      { "file": "SOUL.md", "description": "Agent personality and behavioral guidelines", "bytes": 2027 },
      { "file": "AGENTS.md", "description": "Agent definitions, routing rules, personas", "bytes": 8413 }
    ],
    "knowledge": ["FUNNELS.md", "WORKFLOWS.md"],
    "templates": ["BRIEF_FORMAT.md"],
    "projects": [
      { "project": "mamme-imprenditrici", "files": ["SPECS.md"] },
      { "project": "finanza", "files": ["SPECS.md"] }
    ]
  }
}
```

### Migra tutto

```bash
poetry run python3 scripts/memory_ops.py migrate all --workspace ~/.openclaw/workspace --agent-id default
```

Se ometti `--workspace`, usa il default `~/.openclaw/workspace`. Se ometti `--agent-id`, usa `default`.

`migrate all` chiama anche `seed-boot` automaticamente: al termine della migrazione, BOOT.md conterra' il seme per il recovery dell'identita'.

### Migra singole sorgenti

```bash
# Solo workspace files (SOUL.md, TOOLS.md, ecc.) → agent_config
poetry run python3 scripts/memory_ops.py migrate workspace-files --workspace ~/.openclaw/workspace --agent-id default

# Solo knowledge/
poetry run python3 scripts/memory_ops.py migrate knowledge --workspace ~/.openclaw/workspace

# Solo templates/
poetry run python3 scripts/memory_ops.py migrate templates --workspace ~/.openclaw/workspace

# Solo projects/
poetry run python3 scripts/memory_ops.py migrate projects --workspace ~/.openclaw/workspace

# Solo MEMORY.md (con dominio custom)
poetry run python3 scripts/memory_ops.py migrate memory-md --workspace ~/.openclaw/workspace --domain my-agent

# Solo daily logs
poetry run python3 scripts/memory_ops.py migrate daily-logs --workspace ~/.openclaw/workspace --domain my-agent
```

### Idempotenza

La migrazione e' sicura da rieseguire:

- **workspace-files**: upsert su `type`+`agent_id` in `agent_config` — aggiorna se esiste, crea se nuovo
- **seeds**: se un seed con lo stesso `name` esiste gia', viene saltato
- **memories**: se una memory con lo stesso `content`+`domain` esiste gia', viene saltata

```json
{ "upserted": 2, "updated": 0, "skipped": 0, "source": "...", "agent_id": "default", "type": "workspace-files" }
```

### Workspace remoto via SSH

Se il workspace OpenClaw e' su un server remoto, puoi copiarlo localmente e poi migrare:

```bash
# Copia il workspace
ssh user@host "tar czf /tmp/ws.tar.gz -C ~/.openclaw workspace"
scp user@host:/tmp/ws.tar.gz /tmp/
tar xzf /tmp/ws.tar.gz -C /tmp/

# Migra dal workspace locale
poetry run python3 scripts/memory_ops.py migrate all --workspace /tmp/workspace
```

---

## Test

### Suite automatica (206 test)

```bash
# Avvia MongoDB locale
docker compose -f tests/docker-compose.yml up -d

# Lancia tutti i test
poetry run python3 tests/test_all.py

# Ferma
docker compose -f tests/docker-compose.yml down
```

`test_all.py` usa un database dedicato (`mongobrain_test_auto`) che viene droppato a ogni run. Copre:

| Suite | Cosa testa | Test |
|-------|-----------|------|
| Memories | Store, dedup, search, expiry, prune, valori default | 12 |
| Guidelines | Store, dedup, search, deactivate, filtro active | 8 |
| Seeds | Store, dedup, search, export/import round-trip | 10 |
| Agent Config | Create, upsert, get all/single, export/import, clone agent, boot type | 17 |
| Skills | Store, dedup, get, match, activate/deactivate, search --active-only | 16 |
| Skills import | Full doc, prompt_base, unified seed/guideline schema, agent field, MCP tools, export round-trip | 27 |
| Migration | Scan, workspace files → agent_config, file piccoli saltati, idempotenza, knowledge, MEMORY.md, daily logs | 13 |
| Seed-Boot | Creazione BOOT.md, idempotenza, append a file esistente, integrazione con migrate all | 9 |
| Skill-Builder | Starter skill dal setup, 9 guidelines, 2 seeds, 5 tools, triggers, idempotenza re-setup | 44 |
| Edge cases | Tutte le categorie, tutti i tipi config, caratteri speciali, depends_on, search limit | 20 |
| Chat simulation | Flusso completo: load config → search → match-skill → remember → correzione → store guideline → agent delegation | 10 |

### Manualmente

```bash
# Store + search
poetry run python3 scripts/memory_ops.py store memory --content "Test fact" --category fact --domain test
poetry run python3 scripts/memory_ops.py search memory --query "test" --domain test

# Dedup (deve fallire)
poetry run python3 scripts/memory_ops.py store memory --content "Test fact" --category fact --domain test

# Export/import round-trip
poetry run python3 scripts/memory_ops.py store seed --name "test-seed" --description "Test" --content "Content"
poetry run python3 scripts/memory_ops.py export-seeds > /tmp/seeds.json
poetry run python3 scripts/memory_ops.py import-seeds --file /tmp/seeds.json

# Import skill completa (esempio con fixture di test)
poetry run python3 scripts/memory_ops.py import-skills --file tests/fixtures/k8s-cluster-setup.json
poetry run python3 scripts/memory_ops.py get-skill --name "k8s-cluster-setup"
poetry run python3 scripts/memory_ops.py match-skill --trigger "kubernetes cluster"
```

---

## Backup e restore

```bash
# Backup completo
mongodump --db openclaw_memory --out backup/

# Restore
mongorestore --db openclaw_memory backup/openclaw_memory/

# Backup solo seeds (portabile, JSON)
poetry run python3 scripts/memory_ops.py export-seeds > backup-seeds.json
```
