# WP-055: Fix Long-Rest Edge Discovery Reporting Mismatch — Design

## Goal

Make `edges_discovered` in the long-rest response accurately reflect how many `RELATED_TO` edges were actually written to the graph during that run.

## Background

A live run on 2026-03-27 reported `edges_discovered=8`, but graph inspection found 15 `RELATED_TO` edges stamped with the same long-rest timestamp and `activation_count=0`. The reported count was an undercount of actual writes.

## Root Cause

The current implementation accumulates `edges_discovered` by summing `count(r)` from each per-node MERGE query in a Python loop:

```python
edges_discovered = 0
for node in strong_nodes:
    result = session.run("""
        ...
        MERGE (src)-[r:RELATED_TO]->(candidate)
        ON CREATE SET r.weight = 1.0 - distance,
                      r.activation_count = 0,
                      r.last_activated_at = $now_iso,
                      r.decay_rate = $edge_decay_rate
        RETURN count(r) AS discovered
    """, ...)
    row = result.single()
    if row:
        edges_discovered += row["discovered"] or 0
```

`count(r)` counts all rows returned by MERGE — both ON CREATE (new edge) and ON MATCH (existing edge) cases. The `WHERE existing IS NULL` guard filters only the outgoing direction `(src)-[:RELATED_TO]->(candidate)`, so a reverse edge created by a prior iteration is not detected, and the MERGE creates `(candidate)-[:RELATED_TO]->(src)` as a new edge but the original may or may not have already been counted. The net result is that the accumulated Python count diverges from the number of edges actually written.

## Fix

Replace the per-node accumulation in the **live path** with a single post-loop count query that directly measures what was written:

```cypher
MATCH ()-[r:RELATED_TO]->()
WHERE r.last_activated_at = $now_iso AND r.activation_count = 0
RETURN count(r) AS edges_discovered
```

This query runs once after the rediscovery loop completes. It counts exactly the edges stamped with this run's `now_iso` timestamp and `activation_count = 0` — the same two properties set by `ON CREATE SET` in the MERGE. This is the same criterion a human would use to verify the count in the graph, so the reported value and the verifiable value are always identical by construction.

The per-node `edges_discovered += ...` accumulation is removed from the live path entirely.

## Dry-Run Path

The dry-run path is unchanged. It accumulates `would_discover` counts per node as a forward-looking estimate. It does not write to the graph, so there is nothing to verify after the fact. The existing accumulation is correct for its purpose.

## Files Changed

| File | Change |
|------|--------|
| `memory_service/memory_repo.py` | Remove per-node accumulation in live path; add single post-loop count query after the rediscovery loop |
| `tests/test_wp040_maintenance.py` | Add `test_long_rest_edges_discovered_matches_graph` to `TestLongRest`: run long-rest live, then query the graph for edges stamped with the same timestamp + `activation_count=0`, assert the two counts match |

## No-Change Surface

- API response shape (`LongRestResponse`) — unchanged
- Dry-run behaviour — unchanged
- Edge schema — unchanged
- Configuration — unchanged
- `short_rest`, `maintenance_stats`, all other endpoints — unchanged

## Acceptance Criteria

1. After a live long-rest run, `edges_discovered` in the response equals the count of `RELATED_TO` edges with `last_activated_at = <run timestamp>` and `activation_count = 0` in the graph.
2. Dry-run still returns a non-negative integer estimate (no regression).
3. All existing `TestLongRest` tests continue to pass.
4. New test `test_long_rest_edges_discovered_matches_graph` passes against the live stack.
