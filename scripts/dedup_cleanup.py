#!/usr/bin/env python3
"""
scripts/dedup_cleanup.py — One-time cleanup: merge duplicate Memory nodes.

Finds Memory nodes that share an identical fact (case-insensitive) or are
semantically near-identical (cosine distance <= threshold), merges each
group into the canonical node (oldest created_at; tie-break: highest
importance), and reinforces the canonical once to record the significance
of repeated writes.

Usage:
    python scripts/dedup_cleanup.py [--dry-run] [--similarity-threshold FLOAT]

Flags:
    --dry-run                  Print duplicate groups but make no changes.
    --similarity-threshold F   Cosine distance threshold (default 0.05).
"""

import argparse
import math
from collections import defaultdict
from datetime import datetime, timezone

from memory_service.config import Settings, get_driver
from memory_service import memory_repo


def _cosine_distance(a: list, b: list) -> float:
    """Compute cosine distance between two embedding vectors using stdlib math."""
    if not a or not b:
        return 1.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 1.0
    return 1.0 - dot / (norm_a * norm_b)


def _fetch_active_memories(session) -> list[dict]:
    """Return all active Memory nodes with id, fact, created_at, importance, embedding."""
    result = session.run(
        """
        MATCH (m:Memory)
        WHERE (m.status IS NULL OR m.status = 'active')
        RETURN m.id AS id, m.fact AS fact,
               m.created_at AS created_at,
               coalesce(m.importance, 3) AS importance,
               m.embedding AS embedding
        """
    )
    return [dict(r) for r in result]


def _find_exact_groups(memories: list[dict]) -> tuple[list[list[dict]], set[str]]:
    """Group memories by normalised fact text. Returns groups (>1 member) and grouped IDs."""
    buckets: dict[str, list[dict]] = defaultdict(list)
    for m in memories:
        if m["fact"]:
            buckets[m["fact"].lower()].append(m)
    groups = [v for v in buckets.values() if len(v) > 1]
    grouped_ids = {m["id"] for g in groups for m in g}
    return groups, grouped_ids


def _find_semantic_groups(
    memories: list[dict], threshold: float, already_grouped: set[str]
) -> list[list[dict]]:
    """Union-find over remaining memories: group pairs with cosine distance <= threshold."""
    remaining = [m for m in memories if m["id"] not in already_grouped and m["embedding"]]
    if len(remaining) < 2:
        return []

    parent = {m["id"]: m["id"] for m in remaining}
    by_id = {m["id"]: m for m in remaining}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: str, y: str) -> None:
        parent[find(x)] = find(y)

    ids = [m["id"] for m in remaining]
    # O(n²) comparisons — acceptable for one-time cleanup.
    # For very large graphs, replace with HNSW-based batch search.
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = ids[i], ids[j]
            if _cosine_distance(by_id[a]["embedding"], by_id[b]["embedding"]) <= threshold:
                union(a, b)

    clusters: dict[str, list[dict]] = defaultdict(list)
    for mid in ids:
        clusters[find(mid)].append(by_id[mid])

    return [v for v in clusters.values() if len(v) > 1]


def pick_canonical(group: list[dict]) -> dict:
    """Oldest created_at wins; on tie, highest importance wins."""
    return sorted(group, key=lambda m: (m["created_at"] or "", -(m["importance"] or 3)))[0]


def merge_group(
    session, canonical_id: str, duplicate_ids: list[str], settings: Settings
) -> None:
    """Merge each duplicate into canonical, then reinforce canonical once."""
    now_iso = datetime.now(timezone.utc).isoformat()
    for dup_id in duplicate_ids:
        memory_repo.merge_memory(
            session,
            source_id=dup_id,
            target_id=canonical_id,
            strategy="replace",
            default_edge_decay_rate=settings.edge_decay_rate,
        )
    memory_repo.reinforce_memory(
        session,
        canonical_id,
        strength_increment=settings.explicit_strength_increment,
        edge_increment=settings.edge_explicit_increment,
        co_recalled_ids=[],
        now_iso=now_iso,
        consolidated_decay_rate=settings.memory_consolidated_decay_rate,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge duplicate Memory nodes in Memgraph")
    parser.add_argument("--dry-run", action="store_true", help="Print groups but make no changes")
    parser.add_argument(
        "--similarity-threshold",
        type=float,
        default=0.05,
        help="Cosine distance threshold for semantic dedup (default 0.05)",
    )
    args = parser.parse_args()

    settings = Settings()
    driver = get_driver(settings)

    with driver.session() as session:
        memories = _fetch_active_memories(session)

    if not memories:
        print("[dedup] No active Memory nodes found.")
        driver.close()
        return

    exact_groups, grouped_ids = _find_exact_groups(memories)
    semantic_groups = _find_semantic_groups(memories, args.similarity_threshold, grouped_ids)
    all_groups = exact_groups + semantic_groups

    if not all_groups:
        print("[dedup] No duplicate groups found.")
        driver.close()
        return

    total_merges = sum(len(g) - 1 for g in all_groups)
    print(
        f"[dedup] Found {len(all_groups)} duplicate group(s) "
        f"({len(exact_groups)} exact, {len(semantic_groups)} semantic), "
        f"{total_merges} merge(s) to perform."
    )

    if args.dry_run:
        for i, group in enumerate(all_groups, 1):
            canonical = pick_canonical(group)
            dups = [m["id"] for m in group if m["id"] != canonical["id"]]
            kind = "exact" if i <= len(exact_groups) else "semantic"
            print(
                f"  Group {i} [{kind}]: canonical={canonical['id']!r} "
                f"fact={canonical['fact']!r:.60}, duplicates={dups}"
            )
        print("[dedup] Dry-run: no changes made.")
        driver.close()
        return

    performed = 0
    for group in all_groups:
        canonical = pick_canonical(group)
        dup_ids = [m["id"] for m in group if m["id"] != canonical["id"]]
        with driver.session() as session:
            merge_group(session, canonical["id"], dup_ids, settings)
        performed += len(dup_ids)

    print(f"[dedup] Done. {len(all_groups)} groups processed, {performed} merge(s) performed.")
    driver.close()


if __name__ == "__main__":
    main()
