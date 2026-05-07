#!/usr/bin/env python3
"""
scripts/apply_threat_dedup_wp138b.py — Apply calibrated threat dedup threshold.

One-off operational script that retroactively applies the WP-138 calibrated
cosine-distance threshold (0.28) to the existing Threat corpus, merging
cross-report duplicates via POST /knowledge/threats/{id}/merge.

Usage:
    python scripts/apply_threat_dedup_wp138b.py --dry-run
    python scripts/apply_threat_dedup_wp138b.py
    python scripts/apply_threat_dedup_wp138b.py --threshold 0.25 --dry-run
    python scripts/apply_threat_dedup_wp138b.py --force            # override >30 safety gate
    python scripts/apply_threat_dedup_wp138b.py --base-url https://memfabric.carr-it.net

Never called by the running service. Reads config from .env via pydantic-settings.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from memory_service.config import Settings, get_driver


def cosine_similarity_matrix(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Cosine similarity matrix of shape (m, n). Zero-norm rows → zero similarity.

    Inlined from scripts/create_cross_framework_informs.py to avoid a cross-script
    import that breaks when running inside the Docker container (scripts/ is not
    baked into the image). Keep in sync if the canonical version changes (WP-167
    will eventually bake scripts/ into the image, at which point this can be removed).
    """
    a_norms = np.linalg.norm(a, axis=1, keepdims=True)
    b_norms = np.linalg.norm(b, axis=1, keepdims=True)
    a_norm = np.where(a_norms > 0, a / a_norms, 0.0)
    b_norm = np.where(b_norms > 0, b / b_norms, 0.0)
    return (a_norm @ b_norm.T).astype(np.float32)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class SafetyGateError(Exception):
    pass


# ---------------------------------------------------------------------------
# Bolt helpers (reuse calibrate_threat_dedup pattern)
# ---------------------------------------------------------------------------


def _fetch_all_threats(session) -> list[dict]:
    result = session.run(
        """
        MATCH (t:Threat)
        WHERE t.embedding IS NOT NULL
          AND (t.archived IS NULL OR t.archived = false)
        RETURN t.id AS id, t.text AS text, t.tags AS tags,
               t.created_at AS created_at, t.embedding AS embedding
        """
    )
    rows = []
    for r in result:
        rows.append({
            "id": r["id"],
            "text": r["text"] or "",
            "tags": list(r["tags"] or []),
            "created_at": r["created_at"] or "",
            "embedding": list(r["embedding"]),
        })
    return rows


def _fetch_report_membership(session) -> dict[str, set]:
    """Return {threat_id: set_of_report_ids} for all live Threats."""
    result = session.run(
        """
        MATCH (tr:ThreatReport)-[:IDENTIFIES]->(t:Threat)
        WHERE t.archived IS NULL OR t.archived = false
        RETURN t.id AS threat_id, tr.id AS report_id
        """
    )
    membership: dict[str, set] = {}
    for r in result:
        tid = r["threat_id"]
        rid = r["report_id"]
        if tid not in membership:
            membership[tid] = set()
        membership[tid].add(rid)
    return membership


def _fetch_identifies_count(session, threat_id: str) -> int:
    result = session.run(
        """
        MATCH (tr:ThreatReport)-[:IDENTIFIES]->(t:Threat {id: $threat_id})
        RETURN count(tr) AS report_count
        """,
        threat_id=threat_id,
    )
    record = result.single()
    return record["report_count"] if record else 0


def _snapshot_counts(session) -> dict:
    active = session.run(
        "MATCH (t:Threat) WHERE t.archived IS NULL OR t.archived = false "
        "RETURN count(t) AS n"
    ).single()["n"]

    archived = session.run(
        "MATCH (t:Threat) WHERE t.archived = true RETURN count(t) AS n"
    ).single()["n"]

    identifies = session.run(
        "MATCH (:ThreatReport)-[r:IDENTIFIES]->(:Threat) RETURN count(r) AS n"
    ).single()["n"]

    techniques = session.run(
        "MATCH (:Threat)-[r:MAPPED_TO_TECHNIQUE]->(:Framework) RETURN count(r) AS n"
    ).single()["n"]

    return {
        "active_threats": active,
        "archived_threats": archived,
        "identifies_edges": identifies,
        "technique_edges": techniques,
    }


def _check_targets_edges(session) -> int:
    result = session.run(
        "MATCH (t:Threat)-[:TARGETS]->() RETURN count(*) AS n"
    ).single()
    return result["n"] if result else 0


# ---------------------------------------------------------------------------
# Candidate-pair helpers
# ---------------------------------------------------------------------------


def _filter_cross_report(
    pairs: list[tuple], report_membership: dict[str, set]
) -> list[tuple]:
    """Return only pairs where the two threats have disjoint report sets.

    Within-report pairs are logged as unexpected and skipped.
    pair format: (id_a, id_b, distance, similarity)
    """
    filtered = []
    for pair in pairs:
        id_a, id_b = pair[0], pair[1]
        reports_a = report_membership.get(id_a, set())
        reports_b = report_membership.get(id_b, set())
        if reports_a & reports_b:
            print(
                f"  [SKIP within-report] {id_a[:16]}... / {id_b[:16]}... "
                f"(shared reports: {reports_a & reports_b})"
            )
        else:
            filtered.append(pair)
    return filtered


def _build_candidate_pairs(
    threats: list[dict], threshold: float
) -> list[tuple]:
    """Return upper-triangle pairs where cosine distance <= threshold.

    Returns list of (id_a, id_b, distance, similarity).
    """
    if len(threats) < 2:
        return []
    embeddings = np.array([t["embedding"] for t in threats], dtype=np.float32)
    sim_matrix = cosine_similarity_matrix(embeddings, embeddings)
    dist_matrix = 1.0 - sim_matrix
    rows, cols = np.triu_indices(len(threats), k=1)
    pairs = []
    for i, j in zip(rows, cols):
        i, j = int(i), int(j)
        dist = float(dist_matrix[i, j])
        if dist <= threshold:
            pairs.append((
                threats[i]["id"],
                threats[j]["id"],
                dist,
                float(sim_matrix[i, j]),
            ))
    return sorted(pairs, key=lambda p: p[2])


def _check_safety_gate(pairs: list[tuple], force: bool) -> None:
    if len(pairs) > 30 and not force:
        raise SafetyGateError(
            f"Safety gate: {len(pairs)} candidate pairs exceed limit of 30. "
            "Pass --force to override."
        )


# ---------------------------------------------------------------------------
# Canonical selection helpers
# ---------------------------------------------------------------------------


def _pick_canonical(node_a: dict, node_b: dict) -> dict:
    """Return the canonical node (the one that survives).

    Priority:
    1. Higher identifies_count wins.
    2. Tie-break: older created_at wins.
    """
    if node_a["identifies_count"] != node_b["identifies_count"]:
        return node_a if node_a["identifies_count"] > node_b["identifies_count"] else node_b
    # Tie-break: older created_at wins (lex comparison works for ISO timestamps)
    created_a = node_a.get("created_at") or ""
    created_b = node_b.get("created_at") or ""
    return node_a if created_a <= created_b else node_b


def _build_merge_plan(
    candidate_pairs: list[tuple],
    threats: list[dict],
    session,
    force: bool,
) -> list[tuple]:
    """Apply union-find over candidate_pairs to produce a merge plan.

    Returns list of (source_id, canonical_id, distance, similarity).
    """
    _check_safety_gate(candidate_pairs, force)

    # Build lookup: threat_id -> threat dict
    threat_map = {t["id"]: t for t in threats}

    # Union-find
    parent: dict[str, str] = {}

    def _find(x: str) -> str:
        while parent.get(x, x) != x:
            parent[x] = parent.get(parent.get(x, x), parent.get(x, x))
            x = parent.get(x, x)
        return x

    def _union(x: str, y: str) -> None:
        parent[_find(x)] = _find(y)

    # Enrich threats with identifies_count from DB
    id_counts: dict[str, int] = {}
    for pair in candidate_pairs:
        for tid in (pair[0], pair[1]):
            if tid not in id_counts:
                id_counts[tid] = _fetch_identifies_count(session, tid)

    for t in threats:
        if t["id"] not in id_counts:
            id_counts[t["id"]] = 0

    merges = []
    for (id_a, id_b, dist, sim) in candidate_pairs:
        root_a = _find(id_a)
        root_b = _find(id_b)
        if root_a == root_b:
            continue  # already in same component

        # Determine canonical
        node_a = dict(threat_map.get(root_a, {"id": root_a, "created_at": ""}))
        node_b = dict(threat_map.get(root_b, {"id": root_b, "created_at": ""}))
        node_a["identifies_count"] = id_counts.get(root_a, 0)
        node_b["identifies_count"] = id_counts.get(root_b, 0)

        canonical = _pick_canonical(node_a, node_b)
        loser = node_b if canonical["id"] == node_a["id"] else node_a

        _union(loser["id"], canonical["id"])
        merges.append((loser["id"], canonical["id"], dist, sim))

    return merges


# ---------------------------------------------------------------------------
# HTTP execution
# ---------------------------------------------------------------------------


def _get_auth_token() -> str | None:
    token = os.environ.get("MEMFABRIC_MCP_BEARER_TOKEN")
    if token:
        return token
    api_keys = os.environ.get("API_KEYS", "")
    if api_keys:
        return api_keys.split(",")[0].strip()
    return None


def _execute_merges(
    merges: list[tuple],
    base_url: str,
    bearer_token: Optional[str],
    dry_run: bool,
) -> list[dict]:
    """Execute merges via HTTP POST. Returns list of result dicts."""
    if dry_run:
        print("\n[dry-run] No HTTP calls made. Proposed merges:")
        for source_id, canonical_id, dist, sim in merges:
            print(f"  merge {source_id[:16]}... -> {canonical_id[:16]}...  dist={dist:.4f}")
        return []

    results = []
    headers: dict = {}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"

    for source_id, canonical_id, dist, sim in merges:
        url = f"{base_url}/knowledge/threats/{source_id}/merge"
        try:
            resp = httpx.post(
                url,
                json={"target_id": canonical_id},
                headers=headers,
                timeout=30,
            )
            if resp.status_code == 401:
                print(
                    f"  [ERROR 401] Authentication failed for merge {source_id} -> {canonical_id}. "
                    "Check MEMFABRIC_MCP_BEARER_TOKEN or API_KEYS environment variable."
                )
                results.append({"source_id": source_id, "error": "401 Unauthorized"})
                continue
            if resp.status_code != 200:
                print(
                    f"  [ERROR {resp.status_code}] {source_id} -> {canonical_id}: "
                    f"{resp.text[:200]}"
                )
                results.append({
                    "source_id": source_id,
                    "error": f"HTTP {resp.status_code}",
                    "body": resp.text[:200],
                })
                continue
            data = resp.json()
            print(
                f"  [OK] {source_id[:16]}... -> {canonical_id[:16]}...  "
                f"identifies_rewired={data.get('identifies_rewired', '?')}  "
                f"techniques_rewired={data.get('techniques_rewired', '?')}"
            )
            results.append(data)
        except httpx.HTTPError as exc:
            print(f"  [REQUEST ERROR] {source_id} -> {canonical_id}: {exc}")
            results.append({"source_id": source_id, "error": str(exc)})

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply calibrated threat dedup threshold to existing corpus."
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would merge; no writes.")
    parser.add_argument("--force", action="store_true",
                        help="Override the >30-merge safety gate.")
    parser.add_argument("--threshold", type=float, default=0.28,
                        help="Cosine-distance threshold (default 0.28).")
    parser.add_argument("--base-url", default=None,
                        help="API base URL (default from MEMFABRIC_BASE_URL or http://localhost:8000).")
    args = parser.parse_args()

    base_url = (
        args.base_url
        or os.environ.get("MEMFABRIC_BASE_URL", "http://localhost:8000")
    ).rstrip("/")

    cfg = Settings()
    driver = get_driver(cfg)

    try:
        with driver.session() as session:
            # R3 pre-flight: check for TARGETS edges
            targets_count = _check_targets_edges(session)
            if targets_count > 0:
                print(
                    f"[ERROR] Found {targets_count} TARGETS edge(s) on Threat nodes. "
                    "merge_threat does not yet rewire TARGETS edges — add rewiring "
                    "before proceeding. Exiting."
                )
                sys.exit(1)

            # Pre-run snapshot
            pre = _snapshot_counts(session)
            print("\n=== Pre-run snapshot ===")
            print(f"  active_threats   : {pre['active_threats']}")
            print(f"  archived_threats : {pre['archived_threats']}")
            print(f"  identifies_edges : {pre['identifies_edges']}")
            print(f"  technique_edges  : {pre['technique_edges']}")

            # Fetch threats and report membership
            threats = _fetch_all_threats(session)
            report_membership = _fetch_report_membership(session)

            print(f"\nFetched {len(threats)} active Threats with embeddings.")

            # Build candidate pairs
            raw_pairs = _build_candidate_pairs(threats, args.threshold)
            print(f"Raw candidate pairs at threshold {args.threshold}: {len(raw_pairs)}")

            # Filter to cross-report only
            candidate_pairs = _filter_cross_report(raw_pairs, report_membership)
            print(f"Cross-report candidate pairs: {len(candidate_pairs)}")

            # Print candidate list
            threat_text = {t["id"]: t["text"] for t in threats}
            if candidate_pairs:
                print("\nCandidate pairs:")
                for id_a, id_b, dist, sim in candidate_pairs:
                    text_a = threat_text.get(id_a, "")[:60]
                    text_b = threat_text.get(id_b, "")[:60]
                    print(f"  dist={dist:.4f}  A={id_a[:16]}... '{text_a}'")
                    print(f"           B={id_b[:16]}... '{text_b}'")

            # Safety gate check (raises SafetyGateError if >30 without --force)
            try:
                _check_safety_gate(candidate_pairs, args.force)
            except SafetyGateError as exc:
                print(f"\n[SAFETY GATE] {exc}")
                sys.exit(1)

            if not candidate_pairs:
                print("\nNo candidate pairs found. Nothing to merge.")
                if args.dry_run:
                    sys.exit(0)
                # Write empty maintenance log entry
                from memory_service import memory_repo
                memory_repo.append_maintenance_log(session, {
                    "operation": "auto_merge_wp138b",
                    "ran_at": datetime.now(tz=timezone.utc).isoformat(),
                    "threshold": args.threshold,
                    "candidates_found": 0,
                    "merges_attempted": 0,
                    "merges_succeeded": 0,
                    "source_ids": [],
                    "canonical_ids": [],
                })
                sys.exit(0)

            # Build merge plan
            try:
                merge_plan = _build_merge_plan(candidate_pairs, threats, session, args.force)
            except SafetyGateError as exc:
                print(f"\n[SAFETY GATE] {exc}")
                sys.exit(1)

            print(f"\nMerge plan ({len(merge_plan)} merges):")
            for source_id, canonical_id, dist, sim in merge_plan:
                print(f"  merge {source_id[:20]}... -> {canonical_id[:20]}...  dist={dist:.4f}")

        if args.dry_run:
            _execute_merges(merge_plan, base_url, None, dry_run=True)
            print("\n[dry-run complete]")
            sys.exit(0)

        # Execute merges
        bearer_token = _get_auth_token()
        if not bearer_token:
            print(
                "[WARNING] No auth token found. "
                "Set MEMFABRIC_MCP_BEARER_TOKEN or API_KEYS. "
                "Requests may return 401."
            )

        print(f"\nExecuting {len(merge_plan)} merges against {base_url} ...")
        results = _execute_merges(merge_plan, base_url, bearer_token, dry_run=False)

        # Post-run snapshot
        with driver.session() as session:
            post = _snapshot_counts(session)
        print("\n=== Post-run snapshot ===")
        print(f"  active_threats   : {post['active_threats']}  (delta: {post['active_threats'] - pre['active_threats']})")
        print(f"  archived_threats : {post['archived_threats']}  (delta: {post['archived_threats'] - pre['archived_threats']})")
        print(f"  identifies_edges : {post['identifies_edges']}  (delta: {post['identifies_edges'] - pre['identifies_edges']})")
        print(f"  technique_edges  : {post['technique_edges']}  (delta: {post['technique_edges'] - pre['technique_edges']})")

        merges_attempted = len(merge_plan)
        merges_succeeded = sum(1 for r in results if "error" not in r)
        source_ids = [m[0] for m in merge_plan]
        canonical_ids = [m[1] for m in merge_plan]

        print(f"\nMerges attempted: {merges_attempted}  succeeded: {merges_succeeded}")

        # Write maintenance log entry via direct Bolt
        with driver.session() as session:
            from memory_service import memory_repo
            memory_repo.append_maintenance_log(session, {
                "operation": "auto_merge_wp138b",
                "ran_at": datetime.now(tz=timezone.utc).isoformat(),
                "threshold": args.threshold,
                "candidates_found": len(candidate_pairs),
                "merges_attempted": merges_attempted,
                "merges_succeeded": merges_succeeded,
                "source_ids": source_ids,
                "canonical_ids": canonical_ids,
            })
        print("\nMaintenance log entry written.")

    finally:
        driver.close()


if __name__ == "__main__":
    main()
