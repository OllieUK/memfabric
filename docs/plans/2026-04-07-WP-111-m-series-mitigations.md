# WP-111: M-Series ATT&CK Mitigations Ingestion

**Date:** 2026-04-07
**Status:** Ready for implementation

---

## Summary

Parse the 43 `course-of-action` (M-Series) STIX objects already present in
`data/frameworks/enterprise-attack-17.0.json`, create Framework nodes at
`level=mitigation`, link them to the ATT&CK root with CONTAINS edges, write
MITIGATES edges to targeted techniques via direct Cypher (API is label-restricted),
and run embedding similarity to create cross-framework INFORMS edges to ISO/NIST/COBIT.

---

## Key Design Decisions

### 1. New script vs extending `ingest_attack.py`

**Decision: create `scripts/ingest_attack_mitigations.py`.**

Rationale:
- `ingest_attack.py` processes tactics/techniques/sub-techniques; its `main()` is a
  four-step pipeline with a shared `shortname_to_tactic_id` mapping that M-Series
  ingestion does not need.
- M-Series uses a different STIX type (`course-of-action`) and a different STIX
  relationship type (`mitigates`), requiring different parsing logic.
- Separation keeps each script independently re-runnable and idempotent.
- Helper functions `_get_external_id`, `_upsert`, `_add_contains` and `_node_id`
  from `ingest_attack.py` are duplicated (or imported via `importlib`) in the new
  script. Duplication is preferred over cross-script imports in one-off ETL scripts.
- The INFORMS phase is handled by extending `create_cross_framework_informs.py` (see
  decision 3 below), not by the ingestion script.

### 2. MITIGATES edges: API vs direct Cypher

**Decision: write MITIGATES edges directly via the neo4j driver (not the API).**

`knowledge_repo.create_mitigates_edge` uses:
```
MATCH (c:Control {id: $control_id}), (f:Framework {id: $framework_id})
```
Both endpoints of an M-Series MITIGATES edge are `Framework` nodes, not `Control`
nodes. The MATCH will find zero rows and return `None` regardless of whether the
nodes exist. The HTTP route returns 404 in that case.

The correct approach is a direct Cypher MERGE in the script:
```cypher
MATCH (src:Framework {id: $src_id}), (dst:Framework {id: $dst_id})
MERGE (src)-[r:MITIGATES]->(dst)
ON CREATE SET r.created_at = $now
RETURN type(r) AS rel_type
```
This is the same pattern used by `create_cross_framework_informs.py` for
Framework→Framework INFORMS edges. No API change is required for this WP.

### 3. Cross-framework INFORMS: scoping to M-Series only

**Decision: add an `--m-series` flag to `create_cross_framework_informs.py`.**

The existing script fetches nodes by prefix (`_fetch_nodes(session, prefix, levels)`).
Adding M-Series as a source requires:
- prefix: `attack-enterprise.M`
- allowed_levels: `['mitigation']`

A new `--m-series` CLI flag (and corresponding `_ATTACK_MITIGATION_PREFIX` / 
`_ATTACK_MITIGATION_LEVELS` constants) will scope the similarity run to M-Series
nodes only, avoiding a full re-run of all COBIT/ISO/NIST similarity passes.

The existing COBIT/ISO/NIST passes are gated behind `--cobit` flag logic (or run by
default). The `--m-series` flag will be additive: it adds M-Series→ISO, M-Series→NIST,
and M-Series→COBIT similarity passes in the same session. Default threshold of 0.55
is appropriate; M-Series descriptions are defensive-control vocabulary and expected
to cos-sim better than raw ATT&CK technique descriptions.

---

## Approach

### Step 1 — Parse and ingest M-Series Framework nodes (script: `ingest_attack_mitigations.py`)

1. Load STIX bundle via `MitreAttackData`.
2. Call `data.get_objects_by_type("course-of-action")` to get all M-Series objects.
3. Filter: keep only objects where `_get_external_id(obj)` returns a value matching
   `^M\d{4}$` (i.e. source_name=mitre-attack, external_id starts with M).
   Exclude revoked/deprecated: check `obj.get("x_mitre_deprecated")` and
   `obj.get("revoked")`.
4. For each M-Series object:
   - Derive node ID: `attack-enterprise.M{XXXX}` (reuse `_node_id` pattern).
   - POST `{"id": node_id, "title": obj["name"], "level": "mitigation",
     "external_id": ext_id, "domain": "enterprise",
     "parent_id": root_id, "body": description[:2000]}` to `POST /knowledge/frameworks`.
5. Report counts.

### Step 2 — Write MITIGATES edges (direct Cypher in same script)

1. Fetch all STIX relationship objects:
   `data.get_objects_by_type("relationship")`.
2. Filter: `relationship_type == "mitigates"` AND `source_ref` is a
   `course-of-action` STIX ID.
3. Resolve source: find the M-Series node whose STIX ID matches `source_ref`.
   Build a dict `{stix_id: node_id}` during the M-Series parsing pass (Step 1).
4. Resolve target: `target_ref` is a technique/sub-technique STIX ID. Build a
   second dict `{stix_id: node_id}` by iterating `course-of-action` and technique
   objects. Alternatively use `MitreAttackData.get_object_by_stix_id(stix_id)` to
   resolve the technique's external_id at MITIGATES-write time.
5. For each resolved pair, MERGE the MITIGATES edge directly via the neo4j driver
   using the Cypher pattern in Decision 2.
6. Skip silently if either node does not exist in the graph (technique may be
   revoked/deprecated and was not ingested).

### Step 3 — Cross-framework INFORMS edges (extend `create_cross_framework_informs.py`)

1. Add constants:
   ```python
   _ATTACK_MITIGATION_PREFIX = 'attack-enterprise.M'
   _ATTACK_MITIGATION_LEVELS = ['mitigation']
   ```
2. Add `--m-series` CLI flag (bool, default False).
3. When `--m-series` is active:
   - Fetch M-Series nodes via `_fetch_nodes(session, _ATTACK_MITIGATION_PREFIX, _ATTACK_MITIGATION_LEVELS)`.
   - Fetch ISO, NIST, COBIT nodes (reuse existing fetch calls or add new ones).
   - Run `create_informs_edges` for M-Series→ISO, M-Series→NIST, M-Series→COBIT.
4. `--histogram` flag should work for the new passes too.
5. Existing default behaviour (COBIT→ISO, COBIT→NIST) is unchanged.

---

## Affected Files

| File | Change |
|------|--------|
| `scripts/ingest_attack_mitigations.py` | New script: parse course-of-action objects, ingest Framework nodes, write MITIGATES edges via driver |
| `scripts/create_cross_framework_informs.py` | Add `--m-series` flag + M-Series→ISO/NIST/COBIT similarity passes |
| `tests/test_wp111_attack_mitigations.py` | New test file: unit + integration tests |

No changes to `memory_service/` (no API modification needed).

---

## Cypher Patterns

### MITIGATES edge (Framework→Framework)
```cypher
MATCH (src:Framework {id: $src_id}), (dst:Framework {id: $dst_id})
MERGE (src)-[r:MITIGATES]->(dst)
ON CREATE SET r.created_at = $now
RETURN type(r) AS rel_type
```
Parameters: `$src_id` (M-Series node, e.g. `attack-enterprise.M1017`),
`$dst_id` (technique node, e.g. `attack-enterprise.T1566`), `$now` (ISO 8601 UTC string).

### Count M-Series nodes (verification query)
```cypher
MATCH (f:Framework)
WHERE f.id STARTS WITH 'attack-enterprise.M' AND f.level = 'mitigation'
RETURN count(f) AS cnt
```

### Count MITIGATES edges from M-Series
```cypher
MATCH (src:Framework)-[r:MITIGATES]->(dst:Framework)
WHERE src.id STARTS WITH 'attack-enterprise.M'
RETURN count(r) AS cnt
```

### CONTAINS edge (root→M-Series, created via API parent_id)
```cypher
-- Created implicitly by POST /knowledge/frameworks with parent_id=attack-enterprise-v17
MATCH (root:Framework {id: 'attack-enterprise-v17'})-[:CONTAINS]->(m:Framework)
WHERE m.level = 'mitigation'
RETURN count(m) AS cnt
```

### INFORMS edges from M-Series (verification)
```cypher
MATCH (src:Framework)-[r:INFORMS]->(dst:Framework)
WHERE src.id STARTS WITH 'attack-enterprise.M'
  AND r.source = 'embedding-similarity'
RETURN count(r) AS cnt
```

---

## Test Plan

### Unit Tests (`tests/test_wp111_attack_mitigations.py`)

All unit tests use `importlib.util.spec_from_file_location` to load the script
module (pattern from `test_wp106_attack_ingestion.py`). No live stack required.

| Test class | Test cases |
|---|---|
| `TestGetExternalIdMSeries` | `test_returns_m_series_id` — STIX obj with `source_name=mitre-attack, external_id=M1017` returns `"M1017"` |
| `TestGetExternalIdMSeries` | `test_returns_none_for_non_attack_source` — no `mitre-attack` entry returns None |
| `TestMSeriesNodeId` | `test_m1017_maps_to_correct_id` — `_node_id("M1017")` returns `"attack-enterprise.M1017"` |
| `TestMSeriesNodeId` | `test_m1026_maps_to_correct_id` — `_node_id("M1026")` returns `"attack-enterprise.M1026"` |
| `TestParseMitigations` | `test_parse_course_of_action` — given a synthetic STIX object of type `course-of-action`, `_parse_mitigation(obj)` returns correct `{id, title, external_id, body}` dict |
| `TestParseMitigations` | `test_revoked_object_is_excluded` — object with `revoked=True` is filtered out |
| `TestParseMitigations` | `test_deprecated_object_is_excluded` — object with `x_mitre_deprecated=True` is filtered out |
| `TestMitigatesRelationship` | `test_only_mitigates_rel_type_passes` — `relationship_type != "mitigates"` is excluded |
| `TestMitigatesRelationship` | `test_non_course_of_action_source_excluded` — source_ref not in M-Series dict is skipped |
| `TestDryRunMitigations` | `test_dry_run_no_api_calls` — `_upsert(client, ..., dry_run=True)` returns `"dry-run"`, no HTTP call made |

### Integration Tests (require live Memgraph + FastAPI running)

All marked `@pytest.mark.integration`. Use `knowledge_client` and `test_driver`
fixtures from `conftest.py`.

#### Group A: M-Series nodes after ingestion script

| Test class | Test cases |
|---|---|
| `TestMSeriesNodesIngested` | `test_m1017_node_exists` — GET `/knowledge/frameworks/attack-enterprise.M1017` returns 200, `level=mitigation`, `domain=enterprise`, `external_id=M1017` |
| `TestMSeriesNodesIngested` | `test_m_series_count_reasonable` — Cypher count of `Framework` nodes `STARTS WITH 'attack-enterprise.M'` returns ≥ 40 |
| `TestMSeriesNodesIngested` | `test_m_series_nodes_have_embeddings` — Cypher: count nodes `WHERE f.id STARTS WITH 'attack-enterprise.M' AND f.embedding IS NOT NULL` equals total M-Series count |
| `TestMSeriesContainsEdges` | `test_root_contains_m1017` — Cypher: `MATCH (root:Framework {id:'attack-enterprise-v17'})-[:CONTAINS]->(m:Framework {id:'attack-enterprise.M1017'}) RETURN count(*) AS cnt` = 1 |
| `TestMSeriesContainsEdges` | `test_all_m_series_under_root` — Cypher: count `(root)-[:CONTAINS]->(m)` where m.level=mitigation ≥ 40 |

#### Group B: MITIGATES edges

| Test class | Test cases |
|---|---|
| `TestMitigatesEdges` | `test_mitigates_edge_count_reasonable` — Cypher count of MITIGATES edges from M-Series nodes ≥ 100 (MITRE ATT&CK v17 has ~280 mitigates relationships) |
| `TestMitigatesEdges` | `test_known_mitigation_edge` — Cypher: `MATCH (:Framework {id:'attack-enterprise.M1017'})-[:MITIGATES]->(:Framework)` returns ≥ 1 row; M1017 (User Training) mitigates multiple phishing techniques |
| `TestMitigatesEdges` | `test_mitigates_target_is_technique_or_subtechnique` — sample 10 MITIGATES dst nodes; all have level in `{'technique', 'sub-technique'}` |

#### Group C: Cross-framework INFORMS edges

| Test class | Test cases |
|---|---|
| `TestMSeriesInformsEdges` | `test_informs_edges_created` — after running `create_cross_framework_informs.py --m-series`, Cypher count of M-Series INFORMS edges (source=embedding-similarity) > 0 |
| `TestMSeriesInformsEdges` | `test_m_series_informs_iso_or_nist` — at least one M-Series→ISO and one M-Series→NIST INFORMS edge exists |
| `TestMSeriesInformsEdges` | `test_vector_search_finds_m_series` — `POST /knowledge/search/frameworks` with query "user security awareness training phishing" returns at least one hit with id starting `attack-enterprise.M` |

All three integration test groups use `pytest.skip("... not yet ingested")` guards
consistent with `TestAttackHierarchyIngested` pattern from WP-106, so the test suite
can run before the script is executed.

### Acceptance Criteria

1. Exactly 43 (or the actual non-revoked/non-deprecated count from the bundle) M-Series
   Framework nodes exist in the graph with `level=mitigation`, `domain=enterprise`,
   correct `external_id`, non-null `body`, and non-null `embedding`.
2. Each M-Series node has a CONTAINS edge from `attack-enterprise-v17`.
3. ≥ 100 MITIGATES edges exist from M-Series nodes to ATT&CK technique/sub-technique
   Framework nodes (MITRE lists ~280 mitigates relationships in v17).
4. `--dry-run` on `ingest_attack_mitigations.py` reports expected counts without
   writing to the graph.
5. Running `create_cross_framework_informs.py --m-series --dry-run` reports ≥ 1
   candidate pair above threshold 0.55 for at least one of ISO/NIST/COBIT.
6. After running `create_cross_framework_informs.py --m-series`, ≥ 1 INFORMS edge
   exists from an M-Series node to each of ISO 27001 and NIST CSF 2.0.
7. Script is idempotent: re-running either script produces no duplicates (MERGE
   semantics verified by checking node/edge counts before and after second run).
8. All unit tests pass (`pytest tests/test_wp111_attack_mitigations.py -v -k "not integration"`).
9. All integration tests pass against live stack (`pytest tests/test_wp111_attack_mitigations.py -v -m integration`).

---

## Risks / Open Questions

### R1 — Exact M-Series count
The spec says "43 course-of-action objects". The actual non-revoked/non-deprecated
count should be confirmed with a dry-run before writing acceptance criteria as a hard
number. The integration test uses `≥ 40` to tolerate minor version differences.

### R2 — STIX ID resolution for MITIGATES targets
The STIX `relationship.target_ref` is a STIX UUID (e.g.
`attack-pattern--2b742742-28c3-4e1b-bab7-8350d6300fa7`), not an external_id.
The script must resolve STIX UUIDs to Framework node IDs. The recommended approach
is to build a `{stix_id: node_id}` mapping dict during the M-Series and technique
parsing passes. `MitreAttackData.get_object_by_stix_id(stix_id)` is the library
helper if the dict approach is insufficient for any edge case.

### R3 — Techniques in MITIGATES targets that were not ingested
Some techniques in MITIGATES relationships may be revoked/deprecated and therefore
absent from the graph (not ingested by `ingest_attack.py`). The MITIGATES write loop
must skip silently (the MATCH returns no rows; the MERGE is not reached). Test
coverage: `test_mitigates_edge_count_reasonable` lower bound will naturally exclude
these.

### R4 — `--m-series` flag interaction with existing `create_cross_framework_informs.py` behaviour
The existing script defaults to running COBIT→ISO and COBIT→NIST passes. The new
`--m-series` flag should be additive (run M-Series passes in addition to, or
instead of, the COBIT passes). Recommended: make `--m-series` independent. If
neither `--m-series` nor a future `--cobit` flag is passed, the script defaults to
COBIT behaviour (no breaking change). Document this in the script docstring.

### R5 — `create_informs_edge` vs `create_mitigates_edge` in the API
The `/knowledge/informs` endpoint routes Framework→Control (not Framework→Framework).
The `create_informs_edge` Cypher uses `MATCH (f:Framework), (c:Control)`. The
cross-framework INFORMS script bypasses the API entirely (uses direct Cypher
`MATCH (src:Framework), (dst:Framework)`). This is already the established pattern
and requires no change.
