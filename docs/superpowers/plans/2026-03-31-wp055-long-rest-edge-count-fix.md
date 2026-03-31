# WP-055: Fix Long-Rest Edge Discovery Reporting Mismatch — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `edges_discovered` in the long-rest response accurately reflect how many `RELATED_TO` edges were actually written to the graph during that run.

**Architecture:** Remove the per-node `edges_discovered` accumulation from the live path of `long_rest()` in `memory_repo.py`. After the rediscovery loop completes, run one post-loop Cypher query that counts `RELATED_TO` edges whose `last_activated_at` equals the run's `now_iso` timestamp and `activation_count = 0` — the exact properties set by `ON CREATE SET` in the MERGE. Add an integration test that asserts this count matches the live graph.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, neo4j Bolt driver, pytest (integration tests against live Memgraph)

---

## Files

| File | Change |
|------|--------|
| `memory_service/memory_repo.py` | Replace per-node live-path accumulation with a post-loop count query |
| `tests/test_wp040_maintenance.py` | Add `test_long_rest_edges_discovered_matches_graph` to `TestLongRest` |

---

## Task 1: Write the failing test

**Files:**
- Modify: `tests/test_wp040_maintenance.py` (inside `TestLongRest`, after line 229)

The new test creates two semantically similar memories (directly via Cypher, with known embeddings), removes any pre-existing edge between them, runs a live long-rest, then queries the graph for edges stamped with the run's timestamp and `activation_count = 0`. It asserts that the API-reported `edges_discovered` equals the graph count.

The test captures the `now_iso` used by the API call indirectly — it uses the `last_long_rest_at` property written to the System node (which equals the `now_iso` passed to `long_rest()`). The System node is always updated in a live (non-dry-run) run.

- [ ] **Step 1: Add the test method to `TestLongRest`**

  Open `tests/test_wp040_maintenance.py`. After the closing `finally` block of `test_long_rest_edge_rediscovery` (line 229), add:

  ```python
      def test_long_rest_edges_discovered_matches_graph(self, client, test_driver):
          """edges_discovered in the response equals the graph count of edges stamped by this run."""
          from memory_service.embeddings import get_embedding
          m1 = m2 = None
          try:
              emb1 = get_embedding("pineapple upside down cake recipe")
              emb2 = get_embedding("baking an inverted pineapple dessert")
              m1 = f"wp055-count-a-{uuid.uuid4()}"
              m2 = f"wp055-count-b-{uuid.uuid4()}"

              with test_driver.session() as session:
                  for mid, emb, fact in [
                      (m1, emb1, "pineapple upside down cake recipe"),
                      (m2, emb2, "baking an inverted pineapple dessert"),
                  ]:
                      session.run(
                          "CREATE (m:Memory {id: $id, fact: $fact, text: $fact, "
                          "type: 'fact', tags: [], importance: 3, strength: 0.8, "
                          "recall_count: 0, reinforcement_count: 0, "
                          "last_reinforced_at: '2026-01-01T00:00:00+00:00', "
                          "last_used_at: '2026-01-01T00:00:00+00:00', "
                          "decay_rate: 0.01, embedding: $emb})",
                          id=mid, fact=fact, emb=emb,
                      )

              # Remove any pre-existing edges
              with test_driver.session() as session:
                  session.run(
                      "MATCH (a:Memory {id: $a})-[r:RELATED_TO]-(b:Memory {id: $b}) DELETE r",
                      a=m1, b=m2,
                  )

              r = client.post("/memory/maintenance/long-rest")
              assert r.status_code == 200
              reported = r.json()["edges_discovered"]

              # Retrieve the timestamp long_rest used (written to System node)
              with test_driver.session() as session:
                  sys_row = session.run(
                      "MATCH (sys:System {id: 'system'}) RETURN sys.last_long_rest_at AS ts"
                  ).single()
              assert sys_row is not None
              run_ts = sys_row["ts"]

              # Count edges in the graph stamped by this run
              with test_driver.session() as session:
                  count_row = session.run(
                      "MATCH ()-[r:RELATED_TO]->() "
                      "WHERE r.last_activated_at = $ts AND r.activation_count = 0 "
                      "RETURN count(r) AS n",
                      ts=run_ts,
                  ).single()
              graph_count = count_row["n"] if count_row else 0

              assert reported == graph_count, (
                  f"edges_discovered={reported} but graph has {graph_count} "
                  f"edges stamped with ts={run_ts} and activation_count=0"
              )
          finally:
              for mid in [m1, m2]:
                  if mid:
                      with test_driver.session() as session:
                          session.run("MATCH (m:Memory {id: $id}) DETACH DELETE m", id=mid)
  ```

- [ ] **Step 2: Run the new test to confirm it fails (red phase)**

  ```bash
  cd /home/oliver/projects/graph-memory-fabric
  pytest tests/test_wp040_maintenance.py::TestLongRest::test_long_rest_edges_discovered_matches_graph -v
  ```

  Expected: **FAIL** — `AssertionError: edges_discovered=<undercount> but graph has <actual> edges...`

  If it passes immediately, the bug may have already been fixed or the test setup isn't triggering rediscovery (check that the two memories are semantically similar enough and that embeddings are being generated). Do not proceed to Task 2 until the test fails for the right reason.

---

## Task 2: Fix `long_rest()` in `memory_repo.py`

**Files:**
- Modify: `memory_service/memory_repo.py` (lines 1249–1276)

Replace the live-path per-node accumulation with a post-loop count query. The dry-run path is left unchanged.

- [ ] **Step 1: Replace the live-path block**

  Find this block (lines 1249–1276):

  ```python
          else:
              result = session.run(
                  """
                  CALL vector_search.search("mem_embedding_idx", $k, $query_vec)
                  YIELD node AS candidate, distance
                  WITH candidate, distance
                  WHERE candidate.id <> $src_id AND distance < $max_distance
                  MATCH (src:Memory {id: $src_id})
                  OPTIONAL MATCH (src)-[existing:RELATED_TO]->(candidate)
                  WITH src, candidate, existing, distance
                  WHERE existing IS NULL
                  MERGE (src)-[r:RELATED_TO]->(candidate)
                  ON CREATE SET r.weight = 1.0 - distance,
                                r.activation_count = 0,
                                r.last_activated_at = $now_iso,
                                r.decay_rate = $edge_decay_rate
                  RETURN count(r) AS discovered
                  """,
                  k=_AUTO_RELATED_K,
                  query_vec=node["embedding"],
                  src_id=node["id"],
                  max_distance=_AUTO_RELATED_MAX_DISTANCE,
                  now_iso=now_iso,
                  edge_decay_rate=edge_decay_rate,
              )
              row = result.single()
              if row:
                  edges_discovered += row["discovered"] or 0
  ```

  Replace it with (remove the per-node count, just run the MERGE):

  ```python
          else:
              session.run(
                  """
                  CALL vector_search.search("mem_embedding_idx", $k, $query_vec)
                  YIELD node AS candidate, distance
                  WITH candidate, distance
                  WHERE candidate.id <> $src_id AND distance < $max_distance
                  MATCH (src:Memory {id: $src_id})
                  OPTIONAL MATCH (src)-[existing:RELATED_TO]->(candidate)
                  WITH src, candidate, existing, distance
                  WHERE existing IS NULL
                  MERGE (src)-[r:RELATED_TO]->(candidate)
                  ON CREATE SET r.weight = 1.0 - distance,
                                r.activation_count = 0,
                                r.last_activated_at = $now_iso,
                                r.decay_rate = $edge_decay_rate
                  """,
                  k=_AUTO_RELATED_K,
                  query_vec=node["embedding"],
                  src_id=node["id"],
                  max_distance=_AUTO_RELATED_MAX_DISTANCE,
                  now_iso=now_iso,
                  edge_decay_rate=edge_decay_rate,
              )
  ```

  Also remove the `edges_discovered = 0` initialisation line (line 1226) — it will be replaced by the post-loop query result.

- [ ] **Step 2: Add the post-loop count query**

  Immediately after the `for node in strong_nodes:` loop (after the line that was `edges_discovered += row["discovered"] or 0`, now after the `else: session.run(...)` block ends), and before `# Step 3: Weak-edge pruning`, add:

  ```python
      # Count edges written by this run: stamped with now_iso and activation_count=0
      if not dry_run:
          count_row = session.run(
              """
              MATCH ()-[r:RELATED_TO]->()
              WHERE r.last_activated_at = $now_iso AND r.activation_count = 0
              RETURN count(r) AS n
              """,
              now_iso=now_iso,
          ).single()
          edges_discovered = count_row["n"] if count_row else 0
      # dry_run path already accumulated edges_discovered above
  ```

  The full updated block (lines 1226 to just before `# Step 3`) should now look like:

  ```python
      for node in strong_nodes:
          if dry_run:
              # Dry-run: count edges that would be discovered
              result = session.run(
                  """
                  CALL vector_search.search("mem_embedding_idx", $k, $query_vec)
                  YIELD node AS candidate, distance
                  WITH candidate, distance
                  WHERE candidate.id <> $src_id AND distance < $max_distance
                  OPTIONAL MATCH (src:Memory {id: $src_id})-[existing:RELATED_TO]->(candidate)
                  WITH existing
                  WHERE existing IS NULL
                  RETURN count(*) AS would_discover
                  """,
                  k=_AUTO_RELATED_K,
                  query_vec=node["embedding"],
                  src_id=node["id"],
                  max_distance=_AUTO_RELATED_MAX_DISTANCE,
              )
              row = result.single()
              if row:
                  edges_discovered += row["would_discover"] or 0
          else:
              session.run(
                  """
                  CALL vector_search.search("mem_embedding_idx", $k, $query_vec)
                  YIELD node AS candidate, distance
                  WITH candidate, distance
                  WHERE candidate.id <> $src_id AND distance < $max_distance
                  MATCH (src:Memory {id: $src_id})
                  OPTIONAL MATCH (src)-[existing:RELATED_TO]->(candidate)
                  WITH src, candidate, existing, distance
                  WHERE existing IS NULL
                  MERGE (src)-[r:RELATED_TO]->(candidate)
                  ON CREATE SET r.weight = 1.0 - distance,
                                r.activation_count = 0,
                                r.last_activated_at = $now_iso,
                                r.decay_rate = $edge_decay_rate
                  """,
                  k=_AUTO_RELATED_K,
                  query_vec=node["embedding"],
                  src_id=node["id"],
                  max_distance=_AUTO_RELATED_MAX_DISTANCE,
                  now_iso=now_iso,
                  edge_decay_rate=edge_decay_rate,
              )

      # Count edges written by this run: stamped with now_iso and activation_count=0
      edges_discovered = 0
      if not dry_run:
          count_row = session.run(
              """
              MATCH ()-[r:RELATED_TO]->()
              WHERE r.last_activated_at = $now_iso AND r.activation_count = 0
              RETURN count(r) AS n
              """,
              now_iso=now_iso,
          ).single()
          edges_discovered = count_row["n"] if count_row else 0
      # dry_run: edges_discovered already accumulated per-node above
  ```

  Wait — `edges_discovered = 0` was removed from before the loop. To keep the dry_run accumulation working, re-introduce the initialisation at the top of the loop setup, but only use it for dry_run. The cleanest approach: initialise `edges_discovered = 0` before the loop (for the dry_run accumulation), then overwrite it with the post-loop count query only in the live path. Here is the final correct version:

  ```python
      edges_discovered = 0  # accumulated for dry_run; overwritten for live run
      for node in strong_nodes:
          if dry_run:
              result = session.run(
                  """
                  CALL vector_search.search("mem_embedding_idx", $k, $query_vec)
                  YIELD node AS candidate, distance
                  WITH candidate, distance
                  WHERE candidate.id <> $src_id AND distance < $max_distance
                  OPTIONAL MATCH (src:Memory {id: $src_id})-[existing:RELATED_TO]->(candidate)
                  WITH existing
                  WHERE existing IS NULL
                  RETURN count(*) AS would_discover
                  """,
                  k=_AUTO_RELATED_K,
                  query_vec=node["embedding"],
                  src_id=node["id"],
                  max_distance=_AUTO_RELATED_MAX_DISTANCE,
              )
              row = result.single()
              if row:
                  edges_discovered += row["would_discover"] or 0
          else:
              session.run(
                  """
                  CALL vector_search.search("mem_embedding_idx", $k, $query_vec)
                  YIELD node AS candidate, distance
                  WITH candidate, distance
                  WHERE candidate.id <> $src_id AND distance < $max_distance
                  MATCH (src:Memory {id: $src_id})
                  OPTIONAL MATCH (src)-[existing:RELATED_TO]->(candidate)
                  WITH src, candidate, existing, distance
                  WHERE existing IS NULL
                  MERGE (src)-[r:RELATED_TO]->(candidate)
                  ON CREATE SET r.weight = 1.0 - distance,
                                r.activation_count = 0,
                                r.last_activated_at = $now_iso,
                                r.decay_rate = $edge_decay_rate
                  """,
                  k=_AUTO_RELATED_K,
                  query_vec=node["embedding"],
                  src_id=node["id"],
                  max_distance=_AUTO_RELATED_MAX_DISTANCE,
                  now_iso=now_iso,
                  edge_decay_rate=edge_decay_rate,
              )

      if not dry_run:
          count_row = session.run(
              """
              MATCH ()-[r:RELATED_TO]->()
              WHERE r.last_activated_at = $now_iso AND r.activation_count = 0
              RETURN count(r) AS n
              """,
              now_iso=now_iso,
          ).single()
          edges_discovered = count_row["n"] if count_row else 0
  ```

- [ ] **Step 3: Smoke check — service imports cleanly**

  ```bash
  cd /home/oliver/projects/graph-memory-fabric
  python -c "from memory_service.memory_repo import long_rest; print('OK')"
  ```

  Expected output: `OK`

---

## Task 3: Run the tests and commit

**Files:** none new

- [ ] **Step 1: Run the new test (green phase)**

  ```bash
  cd /home/oliver/projects/graph-memory-fabric
  pytest tests/test_wp040_maintenance.py::TestLongRest::test_long_rest_edges_discovered_matches_graph -v
  ```

  Expected: **PASS**

- [ ] **Step 2: Run the full `TestLongRest` suite**

  ```bash
  pytest tests/test_wp040_maintenance.py::TestLongRest -v
  ```

  Expected: all 4 tests PASS (3 existing + 1 new).

- [ ] **Step 3: Run the broader test suite for regressions**

  ```bash
  pytest tests/ -v --ignore=tests/test_wake_up_close_session.py
  ```

  Expected: all tests PASS. (`test_wake_up_close_session.py` requires special setup — skip unless already running.)

- [ ] **Step 4: Move WP-055 to Currently In Progress in BACKLOG.md**

  In `BACKLOG.md`, find the "Currently In Progress" table (or create it if absent) and add:

  ```
  | WP-055 | Fix long-rest edge discovery reporting mismatch | R1 | M | L | — |
  ```

- [ ] **Step 5: Commit**

  ```bash
  cd /home/oliver/projects/graph-memory-fabric
  git add memory_service/memory_repo.py tests/test_wp040_maintenance.py BACKLOG.md
  git commit -m "WP-055: fix long-rest edges_discovered to match actual graph writes"
  ```

---

## Task 4: Mark WP-055 Done in BACKLOG.md and CHANGELOG.md

- [ ] **Step 1: Remove WP-055 from Currently In Progress; add to Completed**

  In `BACKLOG.md`, delete the WP-055 row from "Currently In Progress". Add to the Completed section:

  ```
  | WP-055 | Fix long-rest edge discovery reporting mismatch | 2026-03-31 | Replaced per-node MERGE count with post-loop Cypher count query using timestamp + activation_count=0. edges_discovered now matches verifiable graph state. |
  ```

- [ ] **Step 2: Renumber Order-IDs in Prioritised Backlog**

  WP-055 was at Order-ID 1. Remove it and decrement every subsequent Order-ID by 1 so the sequence stays contiguous.

- [ ] **Step 3: Add entry to `docs/CHANGELOG.md`**

  Following the existing pattern (most recent entry at top), add:

  ```markdown
  ## WP-055 — Fix Long-Rest Edge Discovery Reporting Mismatch (2026-03-31)

  - Replaced per-node `count(r)` accumulation in the live rediscovery path with a single post-loop Cypher count query: `MATCH ()-[r:RELATED_TO]->() WHERE r.last_activated_at = $now_iso AND r.activation_count = 0 RETURN count(r)`
  - `edges_discovered` now equals the count of edges verifiable in the graph by timestamp + activation_count, eliminating the mismatch observed on 2026-03-27 (reported 8, graph had 15)
  - Dry-run path unchanged: continues accumulating `would_discover` per-node as a forward-looking estimate
  - Added `test_long_rest_edges_discovered_matches_graph` integration test to `TestLongRest`

  **Retrospective:** Straightforward single-query replacement. The post-loop count pattern is more trustworthy than per-MERGE accumulation for any future maintenance operations that write edges in bulk.
  ```

- [ ] **Step 4: Final commit**

  ```bash
  cd /home/oliver/projects/graph-memory-fabric
  git add BACKLOG.md docs/CHANGELOG.md
  git commit -m "WP-055: mark Done, update backlog and changelog"
  ```
