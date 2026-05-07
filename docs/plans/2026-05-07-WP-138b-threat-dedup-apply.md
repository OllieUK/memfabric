# WP-138b: Apply Calibrated Dedup Threshold to Existing Threat Corpus

**Date:** 2026-05-07
**Status:** Ready for implementation
**Prerequisite for:** WP-113 (SABSA ingest / JEOPARDISES wiring)

---

## Summary

Apply the WP-138 calibrated cosine-distance threshold (0.28) retrospectively to the 364
Threat nodes already in production, merging cross-report duplicates that were ingested at
the old 0.15 default. This is a one-off operational pass; future ingestion already uses
the new default.

---

## Approach

### Step 1 — Implement `merge_threat` in `memory_service/knowledge_repo.py`

No Threat-merge function exists. Only `memory_repo.merge_memory` exists for `:Memory`
nodes. A purpose-built `merge_threat` must be added to `knowledge_repo.py` following the
same session-scoped, multi-step pattern used by `merge_memory`.

The function signature:

```python
def merge_threat(session, source_id: str, target_id: str) -> dict:
    """Merge source Threat into target Threat.

    Steps (each as a separate session.run call — no DETACH DELETE + RETURN):
    1. Validate both nodes exist and neither is already archived.
    2. Rewire IDENTIFIES edges: for each ThreatReport→source edge, MERGE a
       ThreatReport→target edge. On CREATE copy all four properties (severity,
       confidence, trend, source_terminology). On MATCH (target already has an
       IDENTIFIES edge from the same ThreatReport) keep the existing properties
       unchanged — the canonical report's original assessment wins; do not
       overwrite. Then DELETE the source edge.
    3. Rewire MAPPED_TO_TECHNIQUE edges: for each source→Framework edge,
       MERGE a target→Framework edge (ON CREATE SET created_at; ON MATCH leave
       existing). Then DELETE the source edge.
    4. Archive source: SET source.archived = true, source.merged_into = target_id,
       source.merged_at = <now>.
    5. Return {source_id, target_id, identifies_rewired, techniques_rewired}.
    """
```

**Conflict resolution policy for IDENTIFIES (ON MATCH):** keep existing properties
unchanged. Rationale: the canonical node already has the assessment from one report;
importing the loser's (different) report assessment would create ambiguity about which
report's severity applies. The correct post-condition is that each ThreatReport keeps its
own assessment edge to the canonical node, not that properties are averaged. The
`create_identifies_edge` function's `ON MATCH SET` would overwrite — `merge_threat` must
use a plain `MERGE ... ON CREATE SET` only.

**Cypher gotcha:** `DETACH DELETE` does not support a `RETURN` clause. Count archived
rewirings before deleting edges. Structure is: `MATCH` the source edges into a list,
count them, then `DELETE` in a separate statement. Because Memgraph executes the `MERGE`
and `DELETE` in the same statement correctly (the DELETE applies to the `r` variable
bound in MATCH), the plan uses the `MATCH ... MERGE ... DELETE r` pattern already
established in `merge_memory`.

### Step 2 — Add `POST /knowledge/threats/{threat_id}/merge` endpoint in `knowledge_routes.py`

Pattern exactly mirrors `POST /memory/{memory_id}/merge` in `main.py` (lines 1271–1300):

- Request body: `ThreatMergeRequest(target_id: str)` — a new Pydantic model in
  `knowledge_routes.py`
- Response body: `ThreatMergeResponse(source_id: str, target_id: str,
  identifies_rewired: int, techniques_rewired: int)` — new model
- Route handler: validates source != target, calls `knowledge_repo.merge_threat`, calls
  `memory_repo.append_operation_log` for the audit trail. Does not call
  `append_maintenance_log` — that is reserved for scheduled operations; per-merge audit
  goes into the operation log.
- Import `memory_repo` at the top of the handler (inside the function, keeping ADR-001's
  cross-layer import rule: `knowledge_routes.py` must not import `memory_repo` at module
  level; use a local import as `main.py` does for `knowledge_bridge`).

The operation log entry:

```python
{
    "operation": "merge_threat",
    "source_id": threat_id,
    "target_id": req.target_id,
    "ran_at": now,
    "identifies_rewired": result["identifies_rewired"],
    "techniques_rewired": result["techniques_rewired"],
}
```

### Step 3 — Write `scripts/apply_threat_dedup_wp138b.py`

One-off operational script. Never called by the running service.

**Algorithm:**

1. Fetch all Threat nodes with embeddings via direct Bolt (reuse `_fetch_all_threats`
   pattern from `calibrate_threat_dedup.py`; also fetch the ThreatReport membership
   per Threat via a single `MATCH (tr:ThreatReport)-[:IDENTIFIES]->(t:Threat)` query
   to build a `{threat_id: set[report_id]}` index).
2. Build pairwise distance matrix using `cosine_similarity_matrix` imported from
   `create_cross_framework_informs.py` (same import pattern as `calibrate_threat_dedup.py`
   lines 38–40).
3. Identify candidate pairs: upper-triangle pairs where distance ≤ 0.28 AND the two
   threats have disjoint report sets (cross-report criterion). Within-report duplicates
   would already have been merged at ingest; if any appear they are logged as
   unexpected but skipped (not merged by this script — they should not exist).
4. Pre-run snapshot: print and log Threat node count, IDENTIFIES edge count,
   MAPPED_TO_TECHNIQUE edge count, list of candidate pairs with their IDs, text
   excerpts (first 60 chars), and cosine distance. This is always produced, even in
   dry-run mode.
5. Safety gate: if `len(candidate_pairs) > 30` print a warning listing all pairs, exit
   with code 1. Pass `--force` to override and proceed anyway.
6. Greedy canonical selection over candidate pairs (topological / union-find):
   - Build a union-find over all Threat IDs.
   - Sort candidate pairs by distance ascending (most similar first).
   - For each pair (a, b): if both are in different components, union them. Track which
     node is canonical: fetch IDENTIFIES count for each (a single Cypher COUNT query);
     higher count wins. Tie-break: earlier `created_at` wins. The loser is the source
     (merged into canonical).
   - Result: a list of `(source_id, canonical_id, distance, similarity)` merge tuples.
7. If `--dry-run`: print merge list, exit 0. No HTTP calls made.
8. Execute merges via HTTP: for each `(source_id, canonical_id)` call
   `POST /knowledge/threats/{source_id}/merge` with `{"target_id": canonical_id}`.
   The script uses `requests` with the bearer token from `MEMFABRIC_MCP_BEARER_TOKEN`
   env var (or `API_KEYS` env var as fallback for local testing). Base URL from
   `MEMFABRIC_BASE_URL` env var (default `http://localhost:8000`).
9. Per-merge: print result to stdout. On HTTP error: print full response body and
   continue (do not abort the batch — a single failed merge should not stop the rest).
10. Post-run snapshot: same counts as pre-run. Print delta (nodes archived, edges
    rewired).
11. Write a summary maintenance log entry via `POST /memory/maintenance/log` or direct
    Bolt (the maintenance log endpoint does not exist as a POST; use direct Bolt via
    `memory_repo.append_maintenance_log` in a driver session after the HTTP merge pass).
    Entry format:
    ```json
    {
        "operation": "auto_merge_wp138b",
        "ran_at": "<ISO>",
        "threshold": 0.28,
        "candidates_found": N,
        "merges_attempted": N,
        "merges_succeeded": N,
        "source_ids": [...],
        "canonical_ids": [...]
    }
    ```

**CLI flags:**

| Flag | Behaviour |
|------|-----------|
| `--dry-run` | Print what would merge, no writes. Pre-run snapshot still printed. |
| `--force` | Override the >30-merge safety gate. |
| `--threshold FLOAT` | Override 0.28 (for testing). Default 0.28. |
| `--base-url URL` | Override API base URL. Default from `MEMFABRIC_BASE_URL` env or `http://localhost:8000`. |

**Imports reused:**

- `_fetch_all_threats` pattern from `scripts/calibrate_threat_dedup.py`
- `cosine_similarity_matrix` from `scripts/create_cross_framework_informs.py`
- `memory_repo.append_maintenance_log` (direct Bolt, for the summary entry)
- `Settings`, `get_driver` from `memory_service.config`

### Step 4 — Write `tests/test_wp138b_threat_merge.py`

See Test Plan section below.

---

## Affected Files

| File | Change |
|------|--------|
| `memory_service/knowledge_repo.py` | Add `merge_threat(session, source_id, target_id) -> dict` |
| `memory_service/knowledge_routes.py` | Add `ThreatMergeRequest`, `ThreatMergeResponse` models; add `POST /knowledge/threats/{threat_id}/merge` route |
| `scripts/apply_threat_dedup_wp138b.py` | New script (one-off) |
| `tests/test_wp138b_threat_merge.py` | New test file |
| `BACKLOG.md` | WP-138b ticked Done; WP-113 "Depends on" updated to `WP-138b` |
| `docs/CHANGELOG.md` | Write-back entry |

---

## Cypher Patterns

All queries use named parameters. No DETACH DELETE + RETURN (Memgraph gotcha observed).

### Validate both nodes

```cypher
MATCH (src:Threat {id: $source_id})
WHERE src.archived IS NULL OR src.archived = false
MATCH (tgt:Threat {id: $target_id})
WHERE tgt.archived IS NULL OR tgt.archived = false
RETURN src.id AS src_id
```

Raises `ValueError` if result is None.

### Rewire IDENTIFIES edges (ON CREATE only — keep existing target properties)

```cypher
MATCH (tr:ThreatReport)-[r:IDENTIFIES]->(src:Threat {id: $source_id})
MATCH (tgt:Threat {id: $target_id})
MERGE (tr)-[new_r:IDENTIFIES]->(tgt)
ON CREATE SET
    new_r.severity           = r.severity,
    new_r.confidence         = r.confidence,
    new_r.trend              = r.trend,
    new_r.source_terminology = r.source_terminology,
    new_r.created_at         = r.created_at
DELETE r
RETURN count(new_r) AS identifies_rewired
```

Note: `ON MATCH` is intentionally omitted — if the target already has an IDENTIFIES edge
from the same ThreatReport, the existing properties are preserved unchanged and the
source edge is still deleted. This is the correct semantic: each report retains its own
severity assessment on the canonical node.

### Rewire MAPPED_TO_TECHNIQUE edges

```cypher
MATCH (src:Threat {id: $source_id})-[r:MAPPED_TO_TECHNIQUE]->(f:Framework)
MATCH (tgt:Threat {id: $target_id})
MERGE (tgt)-[new_r:MAPPED_TO_TECHNIQUE]->(f)
ON CREATE SET new_r.created_at = r.created_at
DELETE r
RETURN count(new_r) AS techniques_rewired
```

### Archive source node

```cypher
MATCH (src:Threat {id: $source_id})
SET src.archived   = true,
    src.merged_into = $target_id,
    src.merged_at   = $now
```

Note: properties set separately from the edge rewiring steps so that RETURN counts are
not affected.

### Pre/post snapshot counts

```cypher
MATCH (t:Threat) WHERE t.archived IS NULL OR t.archived = false
RETURN count(t) AS active_threats

MATCH (:ThreatReport)-[r:IDENTIFIES]->(:Threat) RETURN count(r) AS identifies_count

MATCH (:Threat)-[r:MAPPED_TO_TECHNIQUE]->(:Framework) RETURN count(r) AS techniques_count

MATCH (t:Threat) WHERE t.archived = true RETURN count(t) AS archived_threats
```

### IDENTIFIES count per Threat (for canonical selection)

```cypher
MATCH (tr:ThreatReport)-[:IDENTIFIES]->(t:Threat {id: $threat_id})
RETURN count(tr) AS report_count
```

---

## Test Plan

### Unit Tests (no DB, no HTTP — fast)

**File:** `tests/test_wp138b_threat_merge.py`

All unit tests mock the session with `MagicMock()` following the `make_mock_driver()`
pattern in `conftest.py`.

| Test | What it verifies |
|------|-----------------|
| `test_merge_threat_validates_same_id` | `merge_threat(session, "x", "x")` raises `ValueError` before any Cypher runs |
| `test_merge_threat_raises_if_source_not_found` | Session returns None for validation query → `ValueError` raised |
| `test_merge_threat_raises_if_source_archived` | Source node has `archived=true` → `ValueError` raised (validation query filters it out) |
| `test_merge_threat_raises_if_target_archived` | Target node has `archived=true` → `ValueError` raised |
| `test_merge_threat_returns_correct_counts` | Mock session returns `identifies_rewired=3`, `techniques_rewired=2` → returned dict matches |
| `test_merge_threat_calls_archive_step` | Verify `SET src.archived = true` query is called as the final step |

For the script unit tests (no DB, no HTTP):

| Test | What it verifies |
|------|-----------------|
| `test_pick_canonical_higher_identifies_wins` | Node with 5 IDENTIFIES edges selected over node with 2, regardless of age |
| `test_pick_canonical_tiebreak_older_created_at` | Equal IDENTIFIES count → older `created_at` wins |
| `test_safety_gate_triggers_at_31` | `_build_merge_plan` with 31 candidate pairs raises `SafetyGateError` without `--force` |
| `test_safety_gate_bypassed_with_force` | Same input with `force=True` does not raise |
| `test_cross_report_filter_excludes_same_report_pairs` | Two threats from the same ThreatReport are not included as candidates |
| `test_dry_run_makes_no_http_calls` | `requests` is not called when `dry_run=True` |

### Integration Tests (require live Memgraph + FastAPI running)

Mark all with `@pytest.mark.integration`. Use `knowledge_client` fixture (module-scoped,
`ENABLE_KNOWLEDGE_LAYER=true`). Clean up all test Threat/ThreatReport/Framework nodes in
`finally` blocks using `DETACH DELETE` on their IDs directly.

**File:** same `tests/test_wp138b_threat_merge.py`

| Test | Setup | What it verifies |
|------|-------|-----------------|
| `test_merge_threat_rewires_identifies_from_different_reports` | Create ThreatReport A → ThreatA (IDENTIFIES, severity=high), ThreatReport B → ThreatB (IDENTIFIES, severity=medium). Merge ThreatB into ThreatA. | ThreatReport B now has IDENTIFIES → ThreatA with `severity=medium`. ThreatReport A's edge to ThreatA preserved with `severity=high`. ThreatB has `archived=true`, `merged_into=ThreatA.id`. |
| `test_merge_threat_deduplicates_identifies_from_same_report` | Create ThreatReport A → ThreatA (IDENTIFIES), ThreatReport A → ThreatB (IDENTIFIES, severity=low). Merge ThreatB into ThreatA. | ThreatReport A retains exactly ONE IDENTIFIES edge to ThreatA, with original `severity` (not overwritten by loser's `low`). ThreatB archived. |
| `test_merge_threat_rewires_mapped_to_technique` | Create ThreatA → FrameworkX (MAPPED_TO_TECHNIQUE), ThreatB → FrameworkX (MAPPED_TO_TECHNIQUE), ThreatB → FrameworkY. Merge ThreatB into ThreatA. | ThreatA has MAPPED_TO_TECHNIQUE → FrameworkX (one edge, not two). ThreatA has MAPPED_TO_TECHNIQUE → FrameworkY. ThreatB has no outgoing edges. |
| `test_merge_threat_returns_correct_response` | Create two Threats each with one IDENTIFIES edge from different reports and one MAPPED_TO_TECHNIQUE edge. | HTTP 200. `identifies_rewired=1`, `techniques_rewired=1` (the non-duplicate technique). |
| `test_merge_threat_400_same_id` | `POST /knowledge/threats/x/merge` with `target_id=x`. | HTTP 400. |
| `test_merge_threat_404_missing_source` | Source ID does not exist. | HTTP 404. |
| `test_merge_threat_404_archived_source` | Source node has `archived=true`. | HTTP 404. |
| `test_operation_log_entry_written` | Perform merge, then `GET /memory/operation/log`. | Log contains entry with `operation=merge_threat`, `source_id`, `target_id`, `identifies_rewired`, `techniques_rewired`. |

### Acceptance Criteria

1. `POST /knowledge/threats/{source_id}/merge` exists and returns HTTP 200 with
   `{source_id, target_id, identifies_rewired, techniques_rewired}` when source and
   target are both live (non-archived) Threat nodes.
2. After a merge: the source Threat node has `archived=true`, `merged_into=<target_id>`,
   `merged_at` set. It has no outgoing IDENTIFIES or MAPPED_TO_TECHNIQUE edges.
3. All ThreatReport nodes that previously pointed to the source now point to the target.
   No IDENTIFIES edge is duplicated (each ThreatReport has at most one IDENTIFIES edge to
   the target, regardless of how many edges existed across source and target before the
   merge).
4. All Framework nodes previously reached from source via MAPPED_TO_TECHNIQUE are now
   reachable from target. No duplicate MAPPED_TO_TECHNIQUE edge to the same Framework.
5. `GET /memory/operation/log` contains an entry with `operation=merge_threat` for every
   merge performed.
6. `scripts/apply_threat_dedup_wp138b.py --dry-run` prints the pre-run snapshot and
   candidate merge list with no writes to the DB.
7. `scripts/apply_threat_dedup_wp138b.py` without `--dry-run` on the live stack
   (localhost:8000): pre-run and post-run snapshots show reduced active Threat count and
   increased archived count. The delta equals the number of merges executed.
8. After the production run: the maintenance log (via direct Bolt on
   `sys.maintenance_log`) contains a `auto_merge_wp138b` entry with `threshold=0.28` and
   the list of source/canonical IDs.
9. Existing WP-108 tests (`test_wp108_*.py`) and WP-138 tests
   (`test_wp138_threat_dedup_calibration.py`) continue to pass without modification.
10. Post-run active Threat count is ≤ 364 minus merges; all merged nodes carry
    `archived=true`. The merge count does not exceed 30 without `--force` being passed.

---

## Risks / Open Questions

### R1 — Cypher `count()` inside MATCH...MERGE...DELETE pattern

The plan counts rewired edges by returning `count(new_r)` from the same statement that
does the MERGE and DELETE. This is the pattern used in `merge_memory` for RELATED_TO
edges. Validate this works correctly in Memgraph: the count should reflect newly-MERGED
edges, not all edges. If Memgraph's `count()` semantics differ from expected, a
pre-count query (count source edges before the rewire) is a safe fallback and simpler to
reason about. Implementer should verify with a unit test against a real driver.

### R2 — ON MATCH intentionally omitted on IDENTIFIES rewire

The plan specifies no `ON MATCH SET` in the IDENTIFIES rewire Cypher. This means if the
target already has an IDENTIFIES edge from the same ThreatReport, that edge's `severity`,
`confidence`, `trend`, and `source_terminology` are left unchanged. This is the correct
semantic but diverges from `create_identifies_edge` (which uses `ON MATCH SET` to
overwrite). Document this difference clearly in the function docstring so future
maintainers do not "fix" it by copying `create_identifies_edge`'s pattern.

### R3 — TARGETS edges not handled

The Threat node also has outgoing `TARGETS` edges (Threat → Asset). The BACKLOG spec
does not mention rewiring TARGETS edges. Check whether any Threat nodes in production
have TARGETS edges before running. If they do, the archived node will retain dangling
TARGETS edges (pointing to an archived source). Implementer should query
`MATCH (t:Threat)-[:TARGETS]->() RETURN count(*) AS n` before the production run and
flag if > 0 — at that point, add TARGETS rewiring to `merge_threat` before proceeding.
The assumption in this plan is that the 364-threat corpus has no TARGETS edges (the WP-108
ingestion pipeline did not produce them).

### R4 — `list_threats` includes archived nodes

`knowledge_repo.list_threats` returns all Threat nodes with no `archived` filter. After
the merge pass, it will return archived nodes. This is a pre-existing gap not introduced
by WP-138b, but worth flagging: `GET /knowledge/threats` will include `archived=true`
nodes post-run. Add a deferred BACKLOG item (not in scope here) to add an
`?include_archived=false` query param to the list endpoint.

### R5 — Script authentication

The script reads `MEMFABRIC_MCP_BEARER_TOKEN` for production and `API_KEYS` for local
testing. If neither is set and the service has `API_KEYS` configured, the HTTP calls will
return 401. The script should print a clear error message on 401 rather than silently
failing.

### R6 — `conftest.py` `knowledge_client` fixture scope

`knowledge_client` is `scope="module"`. The integration tests must not rely on state
leaking between tests — each test creates its own Threat/ThreatReport/Framework nodes
with unique IDs and cleans them up in a `finally` block. Do not use `autouse` cleanup
that could interfere with the module-scope client.

### R7 — Production run order

Run on localhost:8000 first (with test data) to verify the merge pass works correctly
before targeting `https://memfabric.carr-it.net`. The `--base-url` flag enables this
without changing the script. The BACKLOG DoD requires the pass be executed against
the production fabric — confirm this is done after local verification.
