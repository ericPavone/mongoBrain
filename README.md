# db-bridge

Skill OpenClaw che aggiunge memoria persistente strutturata a qualsiasi agente, usando MongoDB come storage.

Complementa il sistema nativo di OpenClaw (MEMORY.md + daily logs = memoria di sessione) con un database interrogabile che sopravvive tra sessioni, agenti e macchine diverse.

## Come funziona

```
                    OpenClaw Agent
                         │
          ┌──────────────┼──────────────┐
          │              │              │
     MEMORY.md      daily logs     db-bridge
   (scratchpad)   (session-memory)  (MongoDB)
     volatile       per-sessione    persistente
                                    strutturato
                                    portabile
```

L'agente ha 3 tipi di storage nel DB:

| Collection | Cosa contiene | Quando usarla |
|------------|--------------|---------------|
| **memories** | Fatti, preferenze, note, correzioni | L'agente impara qualcosa dalla chat |
| **guidelines** | Procedure, checklist, best practice | L'agente deve seguire regole per un task |
| **seeds** | Pacchetti di conoscenza portabili | Trasferire competenze tra agenti |

### Flusso tipico in una chat

```
1. Sessione inizia
   └→ L'agente cerca nel DB contesto rilevante (memorie + guidelines + seeds)

2. Utente chiede qualcosa
   └→ L'agente cerca nel DB prima di rispondere

3. Utente dice "ricorda che usiamo Traefik"
   └→ L'agente salva come memory (category: fact, source: conversation)

4. Utente corregge: "no, usiamo Caddy non Traefik"
   └→ L'agente salva la correzione (category: feedback, confidence: 1.0)

5. L'agente risolve un problema complesso
   └→ Salva la soluzione come guideline riutilizzabile

6. Utente chiede "cosa sai del nostro stack?"
   └→ L'agente cerca in tutte e 3 le collection e sintetizza

7. Sessione finisce
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
cd db-bridge
poetry install
poetry run python3 scripts/setup_db.py
```

`setup_db.py` crea le 3 collection, tutti gli indici, e un seed starter. E' idempotente: puoi eseguirlo quante volte vuoi.

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
db-bridge/
  SKILL.md                    # Definizione skill OpenClaw + istruzioni per l'agente
  pyproject.toml              # Poetry: dipendenze
  references/
    schemas.md                # Schema completo delle 3 collection + indici
  src/                        # Logica di dominio (vertical slice)
    connection.py             # Connessione MongoDB condivisa + helpers
    memories.py               # Operazioni su memories
    guidelines.py             # Operazioni su guidelines
    seeds.py                  # Operazioni su seeds + export/import
    maintenance.py            # Prune memorie scadute
  src/
    migrate.py                # Migrazione stato nativo OpenClaw → MongoDB
  scripts/                    # Entry point CLI
    setup_db.py               # Crea collection + indici (idempotente)
    memory_ops.py             # CLI con tutti i comandi
  tests/
    docker-compose.yml        # MongoDB locale per test
    skill-pack.json           # Pacchetto seeds di esempio
    sim_chat_flow.py          # Simulazione flusso chat OpenClaw
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
  --difficulty beginner \
  --tags python async
```

**Deduplicazione**: se esiste gia' un documento con lo stesso `content`+`domain` (memory/guideline) o `name` (seed), il comando fallisce con exit 1 e restituisce il documento esistente.

### Search

Ricerca full-text con ranking per rilevanza.

```bash
# Cerca memorie
poetry run python3 scripts/memory_ops.py search memory --query "postgres" --domain infrastructure

# Cerca guidelines (solo quelle attive)
poetry run python3 scripts/memory_ops.py search guideline --query "code review" --task pull-request

# Cerca seeds
poetry run python3 scripts/memory_ops.py search seed --query "async python" --difficulty beginner

# Limita risultati
poetry run python3 scripts/memory_ops.py search memory --query "deploy" --limit 5
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
| `difficulty` | string | no | `intermediate` | `beginner`, `intermediate`, `advanced` |
| `tags` | string[] | no | `[]` | Tag |
| `dependencies` | string[] | no | `[]` | Nomi di seeds prerequisiti |
| `author` | string | no | `""` | Autore |

Tutti i documenti hanno anche `version`, `active` (solo memory/guideline), `created_at`, `updated_at` generati automaticamente.

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
    "difficulty": "beginner",
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
    "difficulty": "beginner",
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
    "difficulty": "intermediate",
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
    "difficulty": "intermediate",
    "tags": ["k8s", "debug", "troubleshooting"],
    "dependencies": ["k8s-core-concepts"],
    "author": "team",
    "version": 1
  }
]
```

2. Importa:

```bash
poetry run python3 scripts/memory_ops.py import-seeds --file packs/kubernetes.json
```

Output:
```json
{ "upserted": 3, "updated": 0, "errors": [] }
```

3. Verifica:

```bash
poetry run python3 scripts/memory_ops.py search seed --query "kubernetes pod" --domain kubernetes
```

### Convenzioni per organizzare i packs

- Un file per dominio: `packs/kubernetes.json`, `packs/aws.json`, `packs/python.json`
- Naming dei seeds: `<dominio>-<topic>`, es. `k8s-core-concepts`, `aws-lambda-basics`
- Usa `dependencies` per creare percorsi: basics → intermediate → advanced
- `difficulty` aiuta l'agente a scegliere il livello giusto per la risposta
- `tags` servono per il filtering, non per la ricerca (la ricerca usa full-text su `name` + `description` + `content`)

### Template vuoto

```json
[
  {
    "name": "",
    "description": "",
    "content": "",
    "domain": "",
    "difficulty": "intermediate",
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

## Come l'agente usa db-bridge (Auto-Learn Protocol)

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

| Sorgente | Destinazione | Dominio |
|----------|-------------|---------|
| `SOUL.md`, `USER.md`, `IDENTITY.md`, `TOOLS.md`, `AGENTS.md`, `HEARTBEAT.md`, `BOOTSTRAP.md` | seeds | `openclaw-config` |
| `knowledge/*.md` | seeds | `openclaw-knowledge` |
| `templates/*.md` | seeds | `openclaw-templates` |
| `projects/<nome>/**/*.md` | seeds (1 seed per progetto, file concatenati) | `openclaw-projects` |
| `MEMORY.md` (sezioni) | memories | `openclaw-memory` |
| `memory/*.md` (daily logs) | memories | `openclaw-daily` |

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
poetry run python3 scripts/memory_ops.py migrate all --workspace ~/.openclaw/workspace
```

Se ometti `--workspace`, usa il default `~/.openclaw/workspace`.

### Migra singole sorgenti

```bash
# Solo workspace files (SOUL.md, TOOLS.md, ecc.)
poetry run python3 scripts/memory_ops.py migrate workspace-files --workspace ~/.openclaw/workspace

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

La migrazione e' sicura da rieseguire: se un seed con lo stesso `name` esiste gia', viene saltato. Se una memory con lo stesso `content`+`domain` esiste gia', viene saltata. L'output indica quanti documenti sono stati migrati e quanti saltati:

```json
{ "migrated": 7, "skipped": 0, "source": "/home/claw/.openclaw/workspace", "type": "workspace-files" }
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

### Con Docker Compose

```bash
# Avvia MongoDB locale
docker compose -f tests/docker-compose.yml up -d

# Setup DB
poetry run python3 scripts/setup_db.py

# Esegui simulazione chat completa
poetry run python3 tests/sim_chat_flow.py

# Ferma
docker compose -f tests/docker-compose.yml down
```

La simulazione (`sim_chat_flow.py`) riproduce un flusso realistico di 12 step:
import skill pack, ricerche contestuali, "ricorda X", correzione feedback, creazione guideline, deduplicazione, cambio sessione.

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

# Prune
poetry run python3 scripts/memory_ops.py store memory --content "Temp" --category note --domain test --expires-at "2020-01-01T00:00:00+00:00"
poetry run python3 scripts/memory_ops.py prune
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
