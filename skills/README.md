# Skills — Guida alla creazione

## Cos'e' una skill

Una skill e' un documento JSON self-contained che contiene tutto il necessario per eseguire un task specifico: procedure, conoscenza, comandi, esempi e riferimenti.

A differenza di guidelines e seeds (che sono pezzi singoli), una skill **aggrega** tutto in un unico pacchetto che l'agente carica e usa come contesto completo.

## Schema del documento

```
{
  name            slug unico (chiave di upsert)
  description     cosa fa, in una riga
  version         intero, per tracciare aggiornamenti
  triggers[]      keyword che attivano la skill
  depends_on[]    nomi di skill prerequisite
  guidelines[]    procedure operative (title, content, task, priority, agent?)
  seeds[]         conoscenza di dominio (name, description, content, difficulty)
  tools[]         comandi eseguibili (name, type?, command, description, config?)
  examples[]      coppie input/output (input, output, description)
  references[]    link utili (url, title, description)
  active          true/false
}
```

## Processo di creazione

### 1. Identifica il task

Parti dalla domanda: "cosa deve saper fare l'agente?"

Esempio: *provisioning di un cluster Kubernetes da zero*.

### 2. Scegli triggers realistici

Pensa a come l'utente chiederebbe questa cosa in chat. Varianti in italiano, inglese, abbreviazioni.

```json
"triggers": ["kubernetes cluster", "k8s setup", "create cluster", "provision k8s"]
```

Regola pratica: 3-6 triggers. Troppo pochi = la skill non viene trovata. Troppi = falsi positivi.

### 3. Scrivi le guidelines (procedure)

Ogni guideline = una fase del task. Ordinale per `priority` (10 = prima, piu' importante).

```
planning    (priority 10)  →  cosa decidere prima di iniziare
provisioning (priority 9)  →  come creare l'infrastruttura
security    (priority 9)   →  hardening
post-install (priority 8)  →  cosa installare dopo
```

Il campo `task` e' una label libera che descrive la fase. L'agente usa `priority` per decidere l'ordine.

Le guidelines rispondono a **come fare**. Devono essere operative: step numerati, comandi concreti, decisioni esplicite.

#### Campo `agent` (opzionale)

Ogni guideline puo' specificare un campo `agent` — un riferimento a chi dovrebbe eseguire quel passo.

```json
{
  "title": "Design mockup in Figma",
  "task": "design",
  "priority": 9,
  "agent": "designer",
  "content": "..."
}
```

`agent` e' un **riferimento soft** che il runtime risolve con questa logica:

```
agent: "designer"
  |
  ├→ 1. Esiste un agente "designer" nel runtime?
  |     (sub-agente OpenClaw, agent type configurato, Claude Code Task agent)
  |     → Delega lo step a quell'agente
  |
  ├→ 2. Esiste una skill "designer" nel DB?
  |     (get-skill --name "designer")
  |     → Carica la skill e usa il suo contesto (guidelines, tools, seeds)
  |     per eseguire lo step
  |
  └→ 3. Nessuno dei due trovato?
        → L'agente corrente esegue lo step usando il content della guideline
```

Questo significa che:
- Le skill funzionano **sempre**, anche senza gli agenti referenziati
- Con gli agenti disponibili diventano piu' capaci (delega specializzata)
- Una skill puo' referenziare un'altra skill come "agente", creando composizione
- Non serve pre-configurare nulla: il fallback e' sempre l'agente corrente

Se `agent` e' assente, lo step lo gestisce l'agente corrente (backward compatible con skill esistenti).

### 4. Scrivi i seeds (conoscenza)

I seeds rispondono a **cosa sapere**. Conoscenza di dominio che non cambia spesso e che serve per prendere decisioni informate.

```
k8s-cluster-architectures     →  managed vs self-hosted, sizing
k8s-networking-fundamentals   →  CNI, CIDR, service mesh
```

`difficulty` aiuta l'agente a calibrare: se l'utente chiede qualcosa di base, usa i seed `beginner`. Se il contesto e' avanzato, usa `advanced`.

### 5. Definisci i tools (comandi)

Comandi che l'agente puo' proporre o eseguire. Usa `<placeholder>` per i parametri variabili.

```json
{
  "name": "kubeconfig-setup",
  "command": "aws eks update-kubeconfig --name <cluster> --region <region>",
  "description": "Configurare kubectl per accedere al cluster"
}
```

#### Campo `type` (opzionale)

I tools possono specificare come vanno invocati:

| Type | Default | Invocazione | Esempio |
|------|---------|------------|---------|
| `cli` | si | Comando shell | `terraform apply`, `npm run build` |
| `mcp` | — | Tool MCP (se il server e' connesso) | `figma_create_file`, `github_create_pr` |
| `api` | — | Richiesta HTTP | `https://api.example.com/v1/check` |
| `manual` | — | Istruzione per l'utente, non eseguibile | "Apri Figma e condividi il link" |

Se `type` e' assente, default a `cli` (backward compatible).

```json
{
  "name": "figma-create-frame",
  "type": "mcp",
  "command": "figma_create_file",
  "description": "Crea un nuovo file Figma",
  "config": { "team_id": "<team-id>" }
}
```

Il campo `config` (opzionale) contiene parametri specifici per tipo: chiavi MCP, header API, ecc.

Tools con `type: "mcp"` sono usabili solo se il server MCP corrispondente e' connesso. Se non lo e', l'agente salta il tool o suggerisce un'alternativa manuale.

### 6. Aggiungi examples (calibrazione)

2-3 coppie input/output che mostrano scenari diversi. L'agente li usa per capire il livello di dettaglio atteso.

Copri almeno:
- Caso standard (produzione)
- Caso semplice (dev/locale)
- Caso edge (opzionale)

### 7. References (opzionale)

Solo link stabili: docs ufficiali, moduli Terraform, RFC. Niente tutorial che spariscono.

## Dipendenze tra skill

`depends_on` crea un grafo di prerequisiti. A runtime, l'agente carica prima le dipendenze.

```
k8s-deploy-app
  └→ depends_on: ["k8s-cluster-setup"]
       └→ depends_on: []
```

Regole:
- Non creare cicli (A dipende da B che dipende da A)
- Tieni le catene corte (max 2-3 livelli)
- Se una skill funziona anche da sola, non aggiungere dipendenze

## Import e verifica

```bash
# Importa
poetry run python3 scripts/memory_ops.py import-skills --file skills/mia-skill.json

# Verifica match per trigger
poetry run python3 scripts/memory_ops.py match-skill --trigger "keyword"

# Carica skill completa
poetry run python3 scripts/memory_ops.py get-skill --name "mia-skill"

# Esporta tutte le skill per backup
poetry run python3 scripts/memory_ops.py export-skills > skills/backup.json
```

`import-skills` usa upsert: se il `name` esiste gia', aggiorna. Se e' nuovo, crea.

Per verificare che tutto funzioni end-to-end (import, get, match, export, agent field, tool type/config):

```bash
docker compose -f tests/docker-compose.yml up -d
poetry run python3 tests/test_all.py
```

La suite importa entrambe le skill di esempio e verifica che i campi `agent` nelle guidelines e `type`/`config` nei tools vengano persistiti e restituiti correttamente.

## Flusso runtime

### Skill senza agent delegation

```
Utente: "Devo creare un cluster Kubernetes su AWS"
  |
  |  1. MATCH
  |  match-skill --trigger "kubernetes cluster"
  |  → trova "k8s-cluster-setup"
  |
  |  2. LOAD
  |  get-skill --name "k8s-cluster-setup"
  |  → carica tutto il documento
  |
  |  3. DEPS (se ci sono)
  |  depends_on non vuoto → carica anche le skill prerequisite
  |
  |  4. EXECUTE
  |  L'agente segue le guidelines in ordine di priority:
  |    priority 10: Pre-flight checklist (planning)
  |    priority  9: Provisioning + Hardening
  |    priority  8: Post-install essentials
  |
  |  Usa i seeds come contesto decisionale
  |  Propone i tools come comandi eseguibili
  |  Calibra il dettaglio sugli examples
  |
  └→ Risposta strutturata all'utente
```

### Skill con agent delegation

```
Utente: "Crea una landing page per il mio SaaS"
  |
  |  1. MATCH → trova "landing-page-creation"
  |  2. LOAD  → carica skill completa
  |
  |  3. EXECUTE con delegation
  |
  |  priority 10 — briefing (agent: "researcher")
  |  └→ "researcher" e' un agente nel runtime? → delega
  |     oppure e' una skill nel DB? → carica contesto
  |     oppure nessuno? → l'agente corrente esegue
  |
  |  priority 9 — design (agent: "designer")
  |  └→ Stessa risoluzione. Se "designer" e' una skill nel DB,
  |     carica i suoi tools MCP (es. figma_create_file) e li usa
  |
  |  priority 9 — copy (agent: "researcher")
  |  └→ Gia' risolto al primo step, riusa lo stesso agente
  |
  |  priority 8 — implementation (agent: "coder")
  |  └→ Delega al coder se disponibile
  |
  |  priority 7 — qa (agent: "reviewer")
  |  └→ Delega al reviewer, usa tool CLI lighthouse
  |
  └→ Risultato composto dai contributi di piu' agenti/skill
```

### Composizione skill-as-agent

Una skill puo' referenziare un'altra skill come `agent`:

```
skill: "landing-page-creation"
  guideline: "Design mockup" → agent: "figma-designer"
                                         |
                                         └→ skill "figma-designer" nel DB
                                              guidelines: come usare Figma
                                              tools: [figma_create_file (mcp), figma_export (mcp)]
                                              seeds: [design-system-patterns]
```

La skill referenziata porta il suo contesto completo. Questo permette di comporre skill complesse da skill piu' piccole e specializzate senza duplicare conoscenza.

## Struttura della directory

```
skills/
  README.md                       ← questo file
  k8s-cluster-setup.json          ← skill senza delegation
  landing-page-creation.json      ← skill con agent delegation + tool MCP
```

Convenzione: un file JSON per skill, nome file = `name` della skill.

## Checklist prima di importare

- [ ] `name` e' uno slug unico, lowercase, con trattini
- [ ] `triggers` coprono le varianti realistiche (3-6)
- [ ] `guidelines` hanno priority coerenti e step operativi
- [ ] `seeds` contengono conoscenza di dominio, non procedure
- [ ] `tools` hanno `<placeholder>` per i parametri variabili
- [ ] `tools` con `type: "mcp"` referenziano tool MCP reali
- [ ] `guidelines` con `agent` referenziano agenti o skill che esistono (o che funzionano come fallback)
- [ ] `examples` coprono almeno 2 scenari diversi
- [ ] `depends_on` non crea cicli
- [ ] Il JSON e' valido (controlla con `python3 -m json.tool < file.json`)
