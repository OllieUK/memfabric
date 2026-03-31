# Fix: GET /strands 500 on bare Strand nodes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix `GET /strands` returning 500 when bare Strand nodes exist in the graph, by preventing bare nodes from being created and making the endpoint degrade gracefully on any that remain.

**Architecture:** Two MERGE→MATCH swaps in `memory_repo.py` prevent bare Strand creation; a WHERE filter in `list_strands` excludes any pre-existing bare nodes; `StrandItem` makes metadata fields optional so the endpoint never 500s on bad data. A one-off cleanup script removes bare nodes from the live DB.

**Tech Stack:** FastAPI, Pydantic v2, neo4j Python driver (Bolt), pytest, FastAPI TestClient

---

## Files

- Modify: `memory_service/memory_repo.py` — two MERGE→MATCH swaps + WHERE filter in list_strands
- Modify: `memory_service/main.py` — StrandItem optional fields
- Create: `scripts/cleanup_bare_strands.py` — one-off Cypher cleanup
- Modify: `tests/test_list_strands.py` — new unit + integration tests

---

### Task 1: StrandItem — make metadata fields optional

**Files:**
- Modify: `memory_service/main.py:243-247`

- [ ] **Step 1: Write the failing unit test**

Add this test class to `tests/test_list_strands.py` (after the existing imports, before `TestListStrandsClient`):

```python
class TestStrandItemModel:
    """Unit tests for StrandItem Pydantic model — no live stack required."""

    def test_strand_item_accepts_none_metadata(self):
        """StrandItem must not raise when name/description/category are None."""
        from memory_service.main import StrandItem
        item = StrandItem(id="strand-bare", name=None, description=None, category=None)
        assert item.id == "strand-bare"
        assert item.name is None
        assert item.description is None
        assert item.category is None

    def test_strand_item_accepts_full_metadata(self):
        from memory_service.main import StrandItem
        item = StrandItem(
            id="strand-core-health",
            name="Health",
            description="Oliver's physical and mental health.",
            category="Core Life Domains",
        )
        assert item.name == "Health"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/oliver/projects/graph-memory-fabric
pytest tests/test_list_strands.py::TestStrandItemModel -v
```

Expected: FAIL — `name` field required, `ValidationError` raised.

- [ ] **Step 3: Make StrandItem fields optional**

In `memory_service/main.py`, replace:

```python
class StrandItem(BaseModel):
    id: str
    name: str
    description: str
    category: str
```

With:

```python
class StrandItem(BaseModel):
    id: str
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
```

(`Optional` is already imported — check the top of `main.py`; if not, add `from typing import Optional` to the existing typing imports.)

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_list_strands.py::TestStrandItemModel -v
```

Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add memory_service/main.py tests/test_list_strands.py
git commit -m "fix: make StrandItem metadata fields Optional to prevent 500 on bare nodes"
```

---

### Task 2: list_strands — filter bare nodes at the repo layer

**Files:**
- Modify: `memory_service/memory_repo.py:350-368`

- [ ] **Step 1: Write the failing unit test**

Add to `tests/test_list_strands.py`, after `TestStrandItemModel`:

```python
class TestListStrandsRepoFilter:
    """Unit tests for list_strands bare-node filtering — uses mock session."""

    def test_bare_nodes_excluded_from_results(self):
        """list_strands must exclude records where name IS NULL."""
        from unittest.mock import MagicMock
        from memory_service.memory_repo import list_strands

        # Simulate a session that returns one bare node and one valid node
        bare_record = {"id": "strand-bare", "name": None, "description": None, "category": None}
        valid_record = {
            "id": "strand-core-health",
            "name": "Health",
            "description": "Physical and mental health.",
            "category": "Core Life Domains",
        }

        mock_session = MagicMock()
        mock_session.run.return_value = [valid_record]  # bare node already filtered by Cypher

        result = list_strands(mock_session)
        assert len(result) == 1
        assert result[0]["id"] == "strand-core-health"
        # Verify the WHERE clause was passed in the query
        call_args = mock_session.run.call_args[0][0]
        assert "IS NOT NULL" in call_args
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_list_strands.py::TestListStrandsRepoFilter -v
```

Expected: FAIL — `"IS NOT NULL"` not found in the current query string.

- [ ] **Step 3: Add WHERE filter to list_strands**

In `memory_service/memory_repo.py`, replace the `list_strands` function body:

```python
def list_strands(session) -> list:
    """Return all Strand nodes with non-null name, ordered by category then name.

    Returns:
        List of dicts with keys: id, name, description, category
    """
    result = session.run(
        "MATCH (s:Strand) WHERE s.name IS NOT NULL "
        "RETURN s.id AS id, s.name AS name, "
        "s.description AS description, s.category AS category "
        "ORDER BY s.category, s.name"
    )
    return [
        {
            "id": record["id"],
            "name": record["name"],
            "description": record["description"],
            "category": record["category"],
        }
        for record in result
    ]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_list_strands.py::TestListStrandsRepoFilter -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add memory_service/memory_repo.py tests/test_list_strands.py
git commit -m "fix: exclude bare Strand nodes from list_strands with WHERE s.name IS NOT NULL"
```

---

### Task 3: add_memory — MERGE → MATCH for strand edges

**Files:**
- Modify: `memory_service/memory_repo.py:101-112`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_list_strands.py`, after `TestListStrandsRepoFilter`:

```python
class TestAddMemoryUnknownStrand:
    """Unit test: add_memory with unknown strand_id must not create a bare Strand node."""

    def test_unknown_strand_id_does_not_create_bare_node(self):
        """MATCH (not MERGE) means no strand node or edge is created for unknown IDs."""
        from unittest.mock import MagicMock, call
        from memory_service import memory_repo

        mock_req = MagicMock()
        mock_req.strand_ids = ["strand-does-not-exist"]
        mock_req.person_ids = []
        mock_req.related_ids = None
        mock_req.fact = "Test fact."
        mock_req.so_what = None
        mock_req.text = "Test fact."
        mock_req.type = "fact"
        mock_req.tags = []
        mock_req.importance = 3
        mock_req.agent_id = "agent-test"

        mock_session = MagicMock()
        mock_session.run.return_value = MagicMock()
        mock_session.run.return_value.single.return_value = None  # no auto-related neighbours

        memory_repo.add_memory(
            mock_session, mock_req,
            memory_id="test-memory-id",
            embedding=[0.1] * 384,
            now="2026-03-31T00:00:00Z",
            decay_rate=0.1,
        )

        # Find the call that handles strand linking
        strand_calls = [
            str(c) for c in mock_session.run.call_args_list
            if "strand-does-not-exist" in str(c)
        ]
        assert len(strand_calls) == 1
        # Must use MATCH, not MERGE
        assert "MATCH" in strand_calls[0]
        assert "MERGE" not in strand_calls[0]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_list_strands.py::TestAddMemoryUnknownStrand -v
```

Expected: FAIL — `"MERGE" not in strand_calls[0]` assertion fails (MERGE is currently used).

- [ ] **Step 3: Swap MERGE → MATCH in add_memory Step 4**

In `memory_service/memory_repo.py`, replace the strand loop in `add_memory` (lines ~102-112):

```python
    # Step 4 — Link to each Strand via IN_STRAND edge (strand must already exist)
    for strand_id in req.strand_ids:
        session.run(
            """
            MATCH (s:Strand {id: $strand_id})
            WITH s
            MATCH (m:Memory {id: $memory_id})
            CREATE (m)-[:IN_STRAND {weight: 1.0}]->(s)
            """,
            strand_id=strand_id,
            memory_id=memory_id,
        )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_list_strands.py::TestAddMemoryUnknownStrand -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add memory_service/memory_repo.py tests/test_list_strands.py
git commit -m "fix: use MATCH (not MERGE) for Strand in add_memory to prevent bare node creation"
```

---

### Task 4: patch_memory — MERGE → MATCH for strand edges

**Files:**
- Modify: `memory_service/memory_repo.py:479-489`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_list_strands.py`:

```python
class TestPatchMemoryUnknownStrand:
    """Unit test: patch_memory strand_ids must not create bare Strand nodes."""

    def test_unknown_strand_id_uses_match_not_merge(self):
        from unittest.mock import MagicMock
        from memory_service import memory_repo

        mock_session = MagicMock()
        mock_session.run.return_value = MagicMock()

        memory_repo.patch_memory(
            mock_session,
            memory_id="test-memory-id",
            patch_fields={"strand_ids": ["strand-does-not-exist"]},
        )

        strand_calls = [
            str(c) for c in mock_session.run.call_args_list
            if "strand-does-not-exist" in str(c)
        ]
        assert len(strand_calls) == 1
        assert "MATCH" in strand_calls[0]
        assert "MERGE" not in strand_calls[0]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_list_strands.py::TestPatchMemoryUnknownStrand -v
```

Expected: FAIL.

- [ ] **Step 3: Swap MERGE → MATCH in patch_memory strand_ids block**

In `memory_service/memory_repo.py`, replace the `for strand_id in patch_fields["strand_ids"]:` loop body (lines ~479-489):

```python
        for strand_id in patch_fields["strand_ids"]:
            session.run(
                """
                MATCH (s:Strand {id: $strand_id})
                WITH s
                MATCH (m:Memory {id: $memory_id})
                CREATE (m)-[:IN_STRAND {weight: 1.0}]->(s)
                """,
                strand_id=strand_id,
                memory_id=memory_id,
            )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_list_strands.py::TestPatchMemoryUnknownStrand -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add memory_service/memory_repo.py tests/test_list_strands.py
git commit -m "fix: use MATCH (not MERGE) for Strand in patch_memory to prevent bare node creation"
```

---

### Task 5: Integration test — unknown strand_id → GET /strands returns 200

**Files:**
- Modify: `tests/test_list_strands.py`

This test requires the live stack (Memgraph + FastAPI). It exercises the full path: POST /memory with unknown strand, then GET /strands.

- [ ] **Step 1: Add integration test**

Add to the `TestGetStrandsIntegration` class in `tests/test_list_strands.py`:

```python
    def test_unknown_strand_id_does_not_cause_500(self, client, test_driver):
        """POST /memory with an unknown strand_id must not pollute GET /strands."""
        # POST with a strand_id that does not exist in the DB
        response = client.post("/memory", json={
            "fact": "Test fact for bare-strand regression.",
            "type": "fact",
            "agent_id": "test-agent-bare-strand",
            "strand_ids": ["strand-does-not-exist-xyz"],
        })
        assert response.status_code == 200
        memory_id = response.json()["memory_id"]

        # GET /strands must return 200 and must not contain the unknown strand
        strands_response = client.get("/strands")
        assert strands_response.status_code == 200
        strand_ids = [s["id"] for s in strands_response.json()["strands"]]
        assert "strand-does-not-exist-xyz" not in strand_ids

        # Cleanup
        with test_driver.session() as session:
            session.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=memory_id)
            # Belt-and-braces: remove bare strand if somehow created
            session.run(
                "MATCH (s:Strand {id: $id}) DETACH DELETE s",
                id="strand-does-not-exist-xyz",
            )
```

- [ ] **Step 2: Run all test_list_strands tests (unit only first)**

```bash
pytest tests/test_list_strands.py -v -k "not Integration"
```

Expected: All unit tests PASS.

- [ ] **Step 3: Run integration tests against live stack**

Ensure Memgraph and FastAPI are running:
```bash
docker ps | grep memgraph
curl -s http://localhost:8000/health | python3 -m json.tool
```

Then:
```bash
pytest tests/test_list_strands.py -v -m integration
```

Expected: All integration tests PASS including the new one.

- [ ] **Step 4: Commit**

```bash
git add tests/test_list_strands.py
git commit -m "test: add integration test for unknown strand_id not causing GET /strands 500"
```

---

### Task 6: Cleanup script for bare Strand nodes

**Files:**
- Create: `scripts/cleanup_bare_strands.py`

- [ ] **Step 1: Create the script**

```python
#!/usr/bin/env python3
"""
scripts/cleanup_bare_strands.py — One-off cleanup: remove bare Strand nodes.

Bare Strand nodes have an id but null name/description/category. They were
created by earlier versions of add_memory/patch_memory that used MERGE instead
of MATCH when linking strand_ids.

Usage:
    python scripts/cleanup_bare_strands.py [--dry-run]

Flags:
    --dry-run    Print bare node IDs but do not delete them.
"""

import argparse
import sys

from memory_service.config import Settings, get_driver


def find_bare_strands(session) -> list[str]:
    result = session.run(
        "MATCH (s:Strand) WHERE s.name IS NULL RETURN s.id AS id"
    )
    return [r["id"] for r in result]


def delete_bare_strands(session) -> int:
    result = session.run(
        "MATCH (s:Strand) WHERE s.name IS NULL DETACH DELETE s RETURN count(s) AS deleted"
    )
    record = result.single()
    return record["deleted"] if record else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove bare Strand nodes from Memgraph")
    parser.add_argument("--dry-run", action="store_true", help="Print only, do not delete")
    args = parser.parse_args()

    settings = Settings()
    driver = get_driver(settings)

    with driver.session() as session:
        bare_ids = find_bare_strands(session)

    if not bare_ids:
        print("[cleanup] No bare Strand nodes found. Nothing to do.")
        driver.close()
        return

    print(f"[cleanup] Found {len(bare_ids)} bare Strand node(s):")
    for sid in bare_ids:
        print(f"  - {sid}")

    if args.dry_run:
        print("[cleanup] Dry-run: no changes made.")
        driver.close()
        return

    with driver.session() as session:
        deleted = delete_bare_strands(session)

    print(f"[cleanup] Deleted {deleted} bare Strand node(s).")
    driver.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify script is importable**

```bash
cd /home/oliver/projects/graph-memory-fabric
python3 -c "import scripts.cleanup_bare_strands; print('OK')"
```

Expected: `OK` (no import errors).

- [ ] **Step 3: Run dry-run against live stack**

```bash
python3 scripts/cleanup_bare_strands.py --dry-run
```

Expected: Either "No bare Strand nodes found" or a list of bare node IDs to be removed.

- [ ] **Step 4: Run actual cleanup (live stack)**

```bash
python3 scripts/cleanup_bare_strands.py
```

Expected: Prints count of deleted nodes (may be 0 if none existed).

- [ ] **Step 5: Commit**

```bash
git add scripts/cleanup_bare_strands.py
git commit -m "script: add cleanup_bare_strands.py to remove legacy bare Strand nodes"
```

---

### Task 7: Full regression run

- [ ] **Step 1: Run all unit tests**

```bash
pytest tests/ -v -k "not Integration and not integration"
```

Expected: All PASS. No regressions.

- [ ] **Step 2: Run all integration tests against live stack**

```bash
pytest tests/ -v -m integration
```

Expected: All PASS. No regressions.

- [ ] **Step 3: Smoke test GET /strands manually**

```bash
curl -s http://localhost:8000/strands | python3 -m json.tool | grep '"id"' | head -5
```

Expected: Returns 20 strands, all with non-null id/name/description/category.

- [ ] **Step 4: Final commit if clean**

If all tests pass and no uncommitted changes remain, the bugfix branch is ready for review.

```bash
git log --oneline -6
```

Expected output (approximate):
```
<hash> test: add integration test for unknown strand_id not causing GET /strands 500
<hash> fix: use MATCH (not MERGE) for Strand in patch_memory to prevent bare node creation
<hash> fix: use MATCH (not MERGE) for Strand in add_memory to prevent bare node creation
<hash> fix: exclude bare Strand nodes from list_strands with WHERE s.name IS NOT NULL
<hash> fix: make StrandItem metadata fields Optional to prevent 500 on bare nodes
<hash> script: add cleanup_bare_strands.py to remove legacy bare Strand nodes
```
