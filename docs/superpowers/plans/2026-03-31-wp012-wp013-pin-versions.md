# WP-012 + WP-013: Pin Dependency and Docker Image Versions

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace open-ended version specifiers in all requirements.txt files with `>=lower,<next_major` bounds, and replace `latest` Docker image tags with explicit `3.9.0` tags.

**Architecture:** Pure config changes — no code touched. All three requirements.txt files get upper-bound ceilings added. docker-compose.yml gets two image tags pinned. The lower bounds already in requirements.txt are preserved exactly; only upper bounds are added.

**Tech Stack:** pip/requirements.txt, Docker Compose

---

### Task 1: Pin memory_service/requirements.txt (WP-012)

**Files:**
- Modify: `memory_service/requirements.txt`

- [ ] **Step 1: Apply the pinned bounds**

Replace the entire file content with:

```
fastapi>=0.111.0,<1
uvicorn[standard]>=0.29.0,<1
neo4j>=5.19.0,<7
sentence-transformers>=3.0.0,<6
pydantic>=2.0.0,<3
pydantic-settings>=2.0.0,<3
python-dotenv>=1.0.0,<2
pytest>=8.0.0,<10
httpx>=0.27.0,<1
```

- [ ] **Step 2: Verify pip still resolves the environment**

```bash
pip check
```

Expected: `No broken requirements` (or similar clean output — no errors about version conflicts).

---

### Task 2: Pin memory_client/requirements.txt (WP-012)

**Files:**
- Modify: `memory_client/requirements.txt`

- [ ] **Step 1: Apply the pinned bounds**

Replace the entire file content with:

```
httpx>=0.27.0,<1
typer>=0.12.0,<1
rich>=13.7.0,<15
pydantic-settings>=2.0.0,<3
respx>=0.20.0,<1
```

- [ ] **Step 2: Verify pip still resolves**

```bash
pip check
```

Expected: `No broken requirements`.

---

### Task 3: Pin mcp_server/requirements.txt (WP-012)

**Files:**
- Modify: `mcp_server/requirements.txt`

- [ ] **Step 1: Apply the pinned bounds**

Replace the entire file content with:

```
fastmcp>=2.0,<4
```

- [ ] **Step 2: Verify pip still resolves**

```bash
pip check
```

Expected: `No broken requirements`.

---

### Task 4: Pin Docker image tags (WP-013)

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Replace both `latest` tags**

In `docker-compose.yml`, make these two changes:

```yaml
# Line 5 — memgraph service
image: memgraph/memgraph-mage:3.9.0

# Line 23 — lab service
image: memgraph/lab:3.9.0
```

- [ ] **Step 2: Verify the file looks correct**

```bash
grep "image:" docker-compose.yml
```

Expected output:
```
    image: memgraph/memgraph-mage:3.9.0
    image: memgraph/lab:3.9.0
```

No `latest` should appear.

---

### Task 5: Update BACKLOG.md and commit

**Files:**
- Modify: `BACKLOG.md`

- [ ] **Step 1: Move WP-012 and WP-013 to Completed in BACKLOG.md**

Remove the two rows for WP-012 and WP-013 from the backlog table. Add entries to the Completed section:

```
| WP-012 | Pin dependency versions in requirements.txt | 2026-03-31 |
| WP-013 | Pin Docker image tags (no `latest`) | 2026-03-31 |
```

- [ ] **Step 2: Commit everything**

```bash
git add memory_service/requirements.txt memory_client/requirements.txt mcp_server/requirements.txt docker-compose.yml BACKLOG.md
git commit -m "WP-012+WP-013: pin requirements and Docker image versions"
```

Expected: commit succeeds with all 5 files in the changeset.
