#!/usr/bin/env python3
"""Automated tests for all mongoBrain operations.

Covers: memories, guidelines, seeds, agent_config, skills, maintenance,
        import/export round-trips, deduplication, edge cases, migration.

Requires a local MongoDB on localhost:27017 (use tests/docker-compose.yml).
Uses a dedicated test database that is dropped at the start of each run.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TEST_DB = "mongobrain_test_auto"
SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
CLI = [sys.executable, str(SCRIPTS / "memory_ops.py")]
SETUP = [sys.executable, str(SCRIPTS / "setup_db.py")]

ENV = {**os.environ, "MONGODB_DB": TEST_DB, "MONGODB_URI": "mongodb://localhost:27017"}

passed = 0
failed = 0
errors: list[str] = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(args: list[str], expect_fail=False) -> dict | list | None:
    result = subprocess.run(
        CLI + args, capture_output=True, text=True, env=ENV, timeout=15
    )
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()

    if expect_fail:
        if result.returncode == 0:
            return {"_unexpected_success": True, "stdout": stdout}
        # Parse stdout even on failure (error JSON goes to stdout via dump_error)
        if stdout:
            try:
                return json.loads(stdout)
            except json.JSONDecodeError:
                return {"_raw": stdout}
        return {"_stderr": stderr}

    if result.returncode != 0:
        raise RuntimeError(f"Command failed: {args}\nstdout: {stdout}\nstderr: {stderr}")

    if not stdout:
        return None
    return json.loads(stdout)


def assert_eq(name, actual, expected):
    global passed, failed
    if actual == expected:
        passed += 1
        print(f"  PASS: {name}")
    else:
        failed += 1
        msg = f"  FAIL: {name} — expected {expected!r}, got {actual!r}"
        errors.append(msg)
        print(msg)


def assert_true(name, condition):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS: {name}")
    else:
        failed += 1
        msg = f"  FAIL: {name}"
        errors.append(msg)
        print(msg)


def assert_contains(name, text, substring):
    global passed, failed
    if substring in str(text):
        passed += 1
        print(f"  PASS: {name}")
    else:
        failed += 1
        msg = f"  FAIL: {name} — '{substring}' not in '{text}'"
        errors.append(msg)
        print(msg)


def write_tmp_json(data) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(data, f, ensure_ascii=False)
    f.close()
    return f.name


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

def setup():
    print("=== SETUP ===")
    # Drop test DB
    from pymongo import MongoClient
    client = MongoClient("mongodb://localhost:27017")
    client.drop_database(TEST_DB)
    print(f"  Dropped database '{TEST_DB}'")

    # Run setup_db.py
    r = subprocess.run(SETUP, capture_output=True, text=True, env=ENV, timeout=15)
    if r.returncode != 0:
        print(f"  setup_db.py failed: {r.stderr}")
        sys.exit(1)
    print("  setup_db.py OK")
    print()


# ---------------------------------------------------------------------------
# Test: Memories
# ---------------------------------------------------------------------------

def test_memories():
    print("=== MEMORIES ===")

    # Store
    doc = run(["store", "memory",
               "--content", "Python 3.12 supports f-string nesting",
               "--category", "fact", "--domain", "python",
               "--tags", "python", "syntax",
               "--confidence", "0.95", "--source", "conversation"])
    assert_true("store memory returns _id", "_id" in doc)
    assert_eq("store memory domain", doc["domain"], "python")
    assert_eq("store memory confidence", doc["confidence"], 0.95)

    # Duplicate → fail
    dup = run(["store", "memory",
               "--content", "Python 3.12 supports f-string nesting",
               "--category", "fact", "--domain", "python"], expect_fail=True)
    assert_contains("duplicate memory rejected", dup, "duplicate")

    # Same content different domain → OK
    doc2 = run(["store", "memory",
                "--content", "Python 3.12 supports f-string nesting",
                "--category", "fact", "--domain", "tips"])
    assert_true("same content different domain OK", "_id" in doc2)

    # Search
    results = run(["search", "memory", "--query", "f-string", "--domain", "python"])
    assert_true("search memory finds results", len(results) > 0)

    # Search no results
    results = run(["search", "memory", "--query", "nonexistent_xyz_123", "--domain", "python"])
    assert_eq("search memory no results", len(results), 0)

    # Store with expiry
    doc3 = run(["store", "memory",
                "--content", "Temporary test note that should expire",
                "--category", "note", "--domain", "test",
                "--expires-at", "2020-01-01T00:00:00+00:00"])
    assert_true("store memory with expiry", doc3["expires_at"] is not None)

    # Prune
    pruned = run(["prune"])
    assert_true("prune deletes expired", pruned["deleted"] >= 1)

    # Store with minimal args (defaults)
    doc4 = run(["store", "memory",
                "--content", "Minimal memory with defaults",
                "--category", "note"])
    assert_eq("default domain is general", doc4["domain"], "general")
    assert_eq("default confidence is 0.8", doc4["confidence"], 0.8)
    assert_eq("default source is manual", doc4["source"], "manual")

    print()


# ---------------------------------------------------------------------------
# Test: Guidelines
# ---------------------------------------------------------------------------

def test_guidelines():
    print("=== GUIDELINES ===")

    # Store
    doc = run(["store", "guideline",
               "--title", "Commit Message Format",
               "--content", "Use conventional commits: type(scope): description",
               "--domain", "git", "--task", "commit",
               "--priority", "9", "--tags", "git", "conventions"])
    assert_true("store guideline returns _id", "_id" in doc)
    assert_eq("guideline priority", doc["priority"], 9)

    # Duplicate content+domain → fail
    dup = run(["store", "guideline",
               "--title", "Different Title Same Content",
               "--content", "Use conventional commits: type(scope): description",
               "--domain", "git"], expect_fail=True)
    assert_contains("duplicate guideline rejected", dup, "duplicate")

    # Same content different domain → OK
    doc2 = run(["store", "guideline",
                "--title", "Commit Format Copy",
                "--content", "Use conventional commits: type(scope): description",
                "--domain", "ci-cd", "--task", "pipeline"])
    assert_true("same content different domain OK", "_id" in doc2)

    # Search
    results = run(["search", "guideline", "--query", "conventional commits"])
    assert_true("search guideline finds results", len(results) > 0)

    # Deactivate
    deact = run(["deactivate", "--title", "Commit Message Format"])
    assert_eq("deactivate count", deact["deactivated"], 1)

    # Search after deactivate (guidelines search filters active=True)
    results = run(["search", "guideline", "--query", "conventional commits", "--domain", "git"])
    assert_eq("deactivated guideline not in search", len(results), 0)

    # Deactivate non-existent → fail
    deact2 = run(["deactivate", "--title", "Non Existent Guideline"], expect_fail=True)
    assert_contains("deactivate missing fails", deact2, "no matching")

    print()


# ---------------------------------------------------------------------------
# Test: Seeds
# ---------------------------------------------------------------------------

def test_seeds():
    print("=== SEEDS ===")

    # Store
    doc = run(["store", "seed",
               "--name", "docker-basics",
               "--description", "Core Docker concepts",
               "--content", "Docker containers package applications with their dependencies",
               "--domain", "devops", "--difficulty", "beginner",
               "--tags", "docker", "containers"])
    assert_true("store seed returns _id", "_id" in doc)
    assert_eq("seed difficulty", doc["difficulty"], "beginner")

    # Duplicate name → fail
    dup = run(["store", "seed",
               "--name", "docker-basics",
               "--description", "Different desc",
               "--content", "Different content but same name"], expect_fail=True)
    assert_contains("duplicate seed rejected", dup, "duplicate")

    # Search
    results = run(["search", "seed", "--query", "Docker containers"])
    assert_true("search seed finds results", len(results) > 0)

    # Export
    exported = run(["export-seeds", "--domain", "devops"])
    assert_true("export seeds returns array", isinstance(exported, list))
    assert_true("exported seed has name", any(s["name"] == "docker-basics" for s in exported))
    assert_true("exported seed no _id", all("_id" not in s for s in exported))

    # Import round-trip
    tmpfile = write_tmp_json(exported)
    imported = run(["import-seeds", "--file", tmpfile])
    os.unlink(tmpfile)
    assert_eq("import seeds no new upserts (already exist)", imported["upserted"], 0)

    # Import new seed via file
    new_seeds = [{"name": "k8s-pods", "description": "Kubernetes Pod basics",
                  "content": "A Pod is the smallest deployable unit in Kubernetes",
                  "domain": "devops", "difficulty": "beginner", "tags": ["k8s"]}]
    tmpfile = write_tmp_json(new_seeds)
    imported = run(["import-seeds", "--file", tmpfile])
    os.unlink(tmpfile)
    assert_eq("import new seed upserted", imported["upserted"], 1)

    # Import with missing name → error
    bad_seeds = [{"description": "no name", "content": "test"}]
    tmpfile = write_tmp_json(bad_seeds)
    imported = run(["import-seeds", "--file", tmpfile])
    os.unlink(tmpfile)
    assert_eq("import missing name counted as error", len(imported["errors"]), 1)

    print()


# ---------------------------------------------------------------------------
# Test: Agent Config
# ---------------------------------------------------------------------------

def test_agent_config():
    print("=== AGENT CONFIG ===")

    # Store (create)
    doc = run(["store", "config", "--type", "soul",
               "--content", "You are a helpful coding assistant.",
               "--agent-id", "test-agent"])
    assert_eq("store config action", doc["_action"], "created")
    assert_eq("config type", doc["type"], "soul")
    assert_eq("config agent_id", doc["agent_id"], "test-agent")

    # Upsert (update)
    doc2 = run(["store", "config", "--type", "soul",
                "--content", "You are a senior Python developer.",
                "--agent-id", "test-agent"])
    assert_eq("upsert config action", doc2["_action"], "updated")
    assert_eq("upsert content changed", doc2["content"], "You are a senior Python developer.")

    # Store another type
    run(["store", "config", "--type", "tools",
         "--content", "Use poetry for package management.",
         "--agent-id", "test-agent"])
    run(["store", "config", "--type", "identity",
         "--content", "Name: TestBot",
         "--agent-id", "test-agent"])
    run(["store", "config", "--type", "boot",
         "--content", "Initialize workspace on startup.",
         "--agent-id", "test-agent"])

    # Get all config
    docs = run(["get-config", "--agent-id", "test-agent"])
    assert_eq("get-config returns 4 sections", len(docs), 4)
    types = {d["type"] for d in docs}
    assert_true("boot type present", "boot" in types)

    # Get single type
    docs = run(["get-config", "--agent-id", "test-agent", "--type", "soul"])
    assert_eq("get-config single type", len(docs), 1)
    assert_eq("get-config content", docs[0]["content"], "You are a senior Python developer.")

    # Get non-existent agent → fail
    err = run(["get-config", "--agent-id", "ghost-agent"], expect_fail=True)
    assert_contains("get-config missing agent fails", err, "no config found")

    # Search config
    results = run(["search", "config", "--query", "Python developer"])
    assert_true("search config finds results", len(results) > 0)

    # Export + import round-trip
    exported = run(["export-config", "--agent-id", "test-agent"])
    assert_true("export config returns array", isinstance(exported, list))
    assert_eq("export config count", len(exported), 4)

    tmpfile = write_tmp_json(exported)
    imported = run(["import-config", "--file", tmpfile, "--agent-id", "cloned-agent"])
    os.unlink(tmpfile)
    assert_eq("import config upserted", imported["upserted"], 4)

    # Verify cloned agent
    cloned = run(["get-config", "--agent-id", "cloned-agent"])
    assert_eq("cloned agent has 4 sections", len(cloned), 4)

    # Import overwrites (not duplicates)
    tmpfile = write_tmp_json(exported)
    imported = run(["import-config", "--file", tmpfile, "--agent-id", "cloned-agent"])
    os.unlink(tmpfile)
    assert_eq("re-import config zero new upserts", imported["upserted"], 0)

    # Default agent-id
    run(["store", "config", "--type", "soul", "--content", "Default agent soul."])
    docs = run(["get-config"])
    assert_true("default agent-id works", any(d["agent_id"] == "default" for d in docs))

    print()


# ---------------------------------------------------------------------------
# Test: Skills
# ---------------------------------------------------------------------------

def test_skills():
    print("=== SKILLS ===")

    # Store minimal
    doc = run(["store", "skill",
               "--name", "test-review",
               "--description", "Test code review skill",
               "--triggers", "review", "code review", "PR review"])
    assert_true("store skill returns _id", "_id" in doc)
    assert_eq("skill triggers count", len(doc["triggers"]), 3)
    assert_eq("skill guidelines empty", doc["guidelines"], [])

    # Duplicate name → fail
    dup = run(["store", "skill",
               "--name", "test-review",
               "--description", "Another"], expect_fail=True)
    assert_contains("duplicate skill rejected", dup, "duplicate")

    # Get skill
    doc = run(["get-skill", "--name", "test-review"])
    assert_eq("get-skill name", doc["name"], "test-review")
    assert_eq("get-skill active", doc["active"], True)

    # Get non-existent skill → fail
    err = run(["get-skill", "--name", "nonexistent-skill"], expect_fail=True)
    assert_contains("get-skill missing fails", err, "not found")

    # Match skill by trigger
    docs = run(["match-skill", "--trigger", "review"])
    assert_true("match-skill finds result", len(docs) > 0)
    assert_eq("match-skill name", docs[0]["name"], "test-review")

    # Match with non-matching trigger → fail
    err = run(["match-skill", "--trigger", "nonexistent_trigger_xyz"], expect_fail=True)
    assert_contains("match-skill no match fails", err, "no skill matches")

    # Deactivate
    run(["deactivate-skill", "--name", "test-review"])
    doc = run(["get-skill", "--name", "test-review"])
    assert_eq("skill deactivated", doc["active"], False)

    # Match deactivated → fail (match only returns active)
    err = run(["match-skill", "--trigger", "review"], expect_fail=True)
    assert_contains("match-skill skips deactivated", err, "no skill matches")

    # Activate
    run(["activate-skill", "--name", "test-review"])
    doc = run(["get-skill", "--name", "test-review"])
    assert_eq("skill reactivated", doc["active"], True)

    # Activate non-existent → fail
    err = run(["activate-skill", "--name", "ghost-skill"], expect_fail=True)
    assert_contains("activate missing fails", err, "not found")

    # Search skill
    results = run(["search", "skill", "--query", "code review"])
    assert_true("search skill finds results", len(results) > 0)

    # Search --active-only
    run(["deactivate-skill", "--name", "test-review"])
    results = run(["search", "skill", "--query", "review", "--active-only"])
    active_names = [r.get("name") for r in results]
    assert_true("search active-only excludes deactivated", "test-review" not in active_names)
    run(["activate-skill", "--name", "test-review"])

    print()


# ---------------------------------------------------------------------------
# Test: Skills import with full document (guidelines, seeds, tools, examples)
# ---------------------------------------------------------------------------

def test_skills_import_full():
    print("=== SKILLS IMPORT (FULL DOCUMENT) ===")

    # Import k8s skill
    k8s_file = str(SKILLS_DIR / "k8s-cluster-setup.json")
    imported = run(["import-skills", "--file", k8s_file])
    assert_eq("import k8s skill upserted", imported["upserted"], 1)
    assert_eq("import k8s skill no errors", len(imported["errors"]), 0)

    # Verify full document
    doc = run(["get-skill", "--name", "k8s-cluster-setup"])
    assert_eq("k8s skill guidelines count", len(doc["guidelines"]), 4)
    assert_eq("k8s skill seeds count", len(doc["seeds"]), 2)
    assert_eq("k8s skill tools count", len(doc["tools"]), 4)
    assert_eq("k8s skill examples count", len(doc["examples"]), 2)
    assert_eq("k8s skill references count", len(doc["references"]), 2)
    assert_true("k8s skill triggers present", len(doc["triggers"]) >= 3)

    # Import landing page skill (has agent + type fields)
    landing_file = str(SKILLS_DIR / "landing-page-creation.json")
    imported = run(["import-skills", "--file", landing_file])
    assert_eq("import landing skill upserted", imported["upserted"], 1)

    # Verify agent field persisted
    doc = run(["get-skill", "--name", "landing-page-creation"])
    agents = [g.get("agent") for g in doc["guidelines"] if g.get("agent")]
    assert_eq("landing skill has 5 agent references", len(agents), 5)
    assert_true("researcher agent referenced", "researcher" in agents)
    assert_true("coder agent referenced", "coder" in agents)
    assert_true("designer agent referenced", "designer" in agents)
    assert_true("reviewer agent referenced", "reviewer" in agents)

    # Verify tool type field persisted
    mcp_tools = [t for t in doc["tools"] if t.get("type") == "mcp"]
    cli_tools = [t for t in doc["tools"] if t.get("type") == "cli"]
    assert_eq("landing skill has 2 MCP tools", len(mcp_tools), 2)
    assert_eq("landing skill has 2 CLI tools", len(cli_tools), 2)
    assert_true("MCP tool has config", "config" in mcp_tools[0])

    # Re-import → update, not duplicate
    imported = run(["import-skills", "--file", k8s_file])
    assert_eq("re-import k8s skill no new upserts", imported["upserted"], 0)

    # Export round-trip
    exported = run(["export-skills"])
    assert_true("export skills returns list", isinstance(exported, list))
    assert_true("export has multiple skills", len(exported) >= 2)
    assert_true("exported no _id", all("_id" not in s for s in exported))

    # Export single skill
    exported_one = run(["export-skills", "--name", "k8s-cluster-setup"])
    assert_eq("export single skill count", len(exported_one), 1)
    assert_eq("export single skill name", exported_one[0]["name"], "k8s-cluster-setup")

    # Import single object (not array)
    single_skill = {"name": "single-import-test", "description": "Test single object import",
                    "triggers": ["single test"]}
    tmpfile = write_tmp_json(single_skill)
    imported = run(["import-skills", "--file", tmpfile])
    os.unlink(tmpfile)
    assert_eq("import single object upserted", imported["upserted"], 1)
    doc = run(["get-skill", "--name", "single-import-test"])
    assert_eq("single import defaults guidelines", doc["guidelines"], [])
    assert_eq("single import defaults active", doc["active"], True)

    # Import with missing name → error
    bad_skill = [{"description": "no name"}]
    tmpfile = write_tmp_json(bad_skill)
    imported = run(["import-skills", "--file", tmpfile])
    os.unlink(tmpfile)
    assert_eq("import missing name error", len(imported["errors"]), 1)

    print()


# ---------------------------------------------------------------------------
# Test: Migration (workspace files → agent_config)
# ---------------------------------------------------------------------------

def test_migration():
    print("=== MIGRATION ===")

    # Create a fake workspace
    tmpdir = tempfile.mkdtemp()
    ws = Path(tmpdir)
    (ws / "SOUL.md").write_text("You are a test agent for migration.", encoding="utf-8")
    (ws / "TOOLS.md").write_text("Use pytest for testing. Use black for formatting.", encoding="utf-8")
    (ws / "BOOT.md").write_text("On startup, load all test fixtures and verify DB connectivity.", encoding="utf-8")
    (ws / "AGENTS.md").write_text("# Agents\n\n## researcher\nResearch specialist.", encoding="utf-8")
    # Small file (< 10 chars) should be skipped
    (ws / "USER.md").write_text("hi", encoding="utf-8")

    # Create knowledge dir
    (ws / "knowledge").mkdir()
    (ws / "knowledge" / "testing.md").write_text("# Testing\n\nAlways write tests before shipping.", encoding="utf-8")

    # Create MEMORY.md
    (ws / "MEMORY.md").write_text("# Stack\n\nWe use Python 3.12 with FastAPI.\n\n# Preferences\n\nPrefer composition over inheritance.", encoding="utf-8")

    # Create daily logs
    (ws / "memory").mkdir()
    (ws / "memory" / "2024-01-15-session.md").write_text("# Tasks\n\nFixed the auth bug in login flow.", encoding="utf-8")

    # Scan (dry run)
    scan_result = run(["migrate", "scan", "--workspace", str(ws)])
    assert_true("scan finds workspace_files", "workspace_files" in scan_result["found"])
    assert_true("scan finds knowledge", "knowledge" in scan_result["found"])
    assert_true("scan finds MEMORY.md", "MEMORY.md" in scan_result["found"])
    assert_true("scan finds daily_logs", "daily_logs" in scan_result["found"])

    # Migrate workspace files → agent_config
    run(["migrate", "workspace-files", "--workspace", str(ws), "--agent-id", "migrate-test"])

    # Verify in agent_config
    docs = run(["get-config", "--agent-id", "migrate-test"])
    types = {d["type"] for d in docs}
    assert_true("migrated soul", "soul" in types)
    assert_true("migrated tools", "tools" in types)
    assert_true("migrated boot", "boot" in types)
    assert_true("migrated agents", "agents" in types)
    # USER.md was < 10 chars → skipped
    assert_true("user.md skipped (too small)", "user" not in types)

    # Idempotent re-run
    # (stdout goes to both migrate prints + dump JSON, parse last JSON line)
    run(["migrate", "workspace-files", "--workspace", str(ws), "--agent-id", "migrate-test"])
    docs = run(["get-config", "--agent-id", "migrate-test"])
    assert_eq("idempotent migrate still 4 sections", len(docs), 4)

    # Migrate knowledge
    run(["migrate", "knowledge", "--workspace", str(ws)])
    results = run(["search", "seed", "--query", "testing"])
    assert_true("knowledge migrated as seed", len(results) > 0)

    # Migrate MEMORY.md
    run(["migrate", "memory-md", "--workspace", str(ws), "--domain", "test-migration"])
    results = run(["search", "memory", "--query", "Python FastAPI"])
    assert_true("memory.md migrated", len(results) > 0)

    # Migrate daily logs
    run(["migrate", "daily-logs", "--workspace", str(ws), "--domain", "test-migration"])
    results = run(["search", "memory", "--query", "auth bug login"])
    assert_true("daily log migrated", len(results) > 0)

    # Cleanup tmpdir
    import shutil
    shutil.rmtree(tmpdir)

    print()


# ---------------------------------------------------------------------------
# Test: Edge cases and cross-collection scenarios
# ---------------------------------------------------------------------------

def test_edge_cases():
    print("=== EDGE CASES ===")

    # Memory with all categories
    for cat in ["fact", "preference", "note", "procedure", "feedback"]:
        doc = run(["store", "memory",
                   "--content", f"Test memory for category {cat} validation",
                   "--category", cat, "--domain", "edge-test"])
        assert_eq(f"category {cat} accepted", doc["category"], cat)

    # Config with all types
    for t in ["soul", "user", "identity", "tools", "agents", "heartbeat", "bootstrap", "boot"]:
        doc = run(["store", "config", "--type", t,
                   "--content", f"Config section for {t}",
                   "--agent-id", "edge-test"])
        assert_eq(f"config type {t} accepted", doc["type"], t)

    # Get all config for edge-test agent
    docs = run(["get-config", "--agent-id", "edge-test"])
    assert_eq("all 8 config types stored", len(docs), 8)

    # Skill with empty triggers and depends_on
    doc = run(["store", "skill",
               "--name", "no-triggers-skill",
               "--description", "Skill with no triggers"])
    assert_eq("skill with no triggers OK", doc["triggers"], [])
    assert_eq("skill with no depends_on OK", doc["depends_on"], [])

    # Skill with depends_on
    doc = run(["store", "skill",
               "--name", "dependent-skill",
               "--description", "Depends on another skill",
               "--depends-on", "test-review", "k8s-cluster-setup"])
    assert_eq("skill depends_on count", len(doc["depends_on"]), 2)

    # Guideline with high priority
    doc = run(["store", "guideline",
               "--title", "Critical Security Rule",
               "--content", "Always validate user input at system boundaries",
               "--domain", "security", "--priority", "10"])
    assert_eq("guideline priority 10", doc["priority"], 10)

    # Memory with special characters in content
    doc = run(["store", "memory",
               "--content", 'User said: "use single quotes" and backslash \\ and newline chars',
               "--category", "feedback", "--domain", "edge-test"])
    assert_true("special chars stored", "backslash" in doc["content"])

    # Seed with dependencies
    doc = run(["store", "seed",
               "--name", "advanced-docker",
               "--description", "Advanced Docker patterns",
               "--content", "Multi-stage builds, BuildKit, layer caching optimization strategies",
               "--domain", "devops", "--difficulty", "advanced",
               "--dependencies", "docker-basics"])
    assert_eq("seed dependencies", doc["dependencies"], ["docker-basics"])

    # Search with limit
    results = run(["search", "memory", "--query", "category", "--limit", "2"])
    assert_true("search limit respected", len(results) <= 2)

    print()


# ---------------------------------------------------------------------------
# Test: Cross-collection workflow (simulate a chat session)
# ---------------------------------------------------------------------------

def test_chat_simulation():
    print("=== CHAT SIMULATION ===")

    # 1. Session starts: load agent config
    docs = run(["get-config", "--agent-id", "edge-test"])
    assert_true("session start: config loaded", len(docs) > 0)

    # 2. User asks about Docker → search memories and seeds
    mem_results = run(["search", "memory", "--query", "Docker", "--domain", "edge-test"])
    seed_results = run(["search", "seed", "--query", "Docker"])
    assert_true("search seeds for Docker", len(seed_results) > 0)

    # 3. User says "do a code review" → match skill
    docs = run(["match-skill", "--trigger", "review"])
    assert_true("match-skill for review", len(docs) > 0)

    skill = run(["get-skill", "--name", docs[0]["name"]])
    assert_true("loaded full skill", "triggers" in skill)

    # 4. User says "remember that we use FastAPI"
    doc = run(["store", "memory",
               "--content", "The project uses FastAPI as the web framework",
               "--category", "fact", "--domain", "chat-sim",
               "--confidence", "0.95", "--source", "conversation"])
    assert_true("remember command stored", "_id" in doc)

    # 5. User corrects: "no, we use Flask not FastAPI"
    doc = run(["store", "memory",
               "--content", "Correction: project uses Flask, NOT FastAPI",
               "--category", "feedback", "--domain", "chat-sim",
               "--confidence", "1.0", "--source", "conversation"])
    assert_eq("correction stored as feedback", doc["category"], "feedback")
    assert_eq("correction confidence 1.0", doc["confidence"], 1.0)

    # 6. After solving a complex problem → store as guideline
    doc = run(["store", "guideline",
               "--title", "MongoDB Connection Pool Tuning",
               "--content", "Set maxPoolSize=50, minPoolSize=5, maxIdleTimeMS=30000 for production",
               "--domain", "mongodb", "--task", "performance",
               "--priority", "8"])
    assert_true("post-task guideline stored", "_id" in doc)

    # 7. Match the landing page skill (with agent delegation)
    docs = run(["match-skill", "--trigger", "landing page"])
    assert_true("match landing page skill", len(docs) > 0)
    skill = run(["get-skill", "--name", "landing-page-creation"])
    agents_in_skill = [g.get("agent") for g in skill["guidelines"]]
    assert_true("skill has agent delegation", any(a for a in agents_in_skill))

    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    setup()

    test_memories()
    test_guidelines()
    test_seeds()
    test_agent_config()
    test_skills()
    test_skills_import_full()
    test_migration()
    test_edge_cases()
    test_chat_simulation()

    print("=" * 60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    if errors:
        print("\nFailed tests:")
        for e in errors:
            print(e)
    print("=" * 60)

    sys.exit(1 if failed > 0 else 0)


if __name__ == "__main__":
    main()
