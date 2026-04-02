"""
migrate_embeddings.py — Re-embed knowledge-layer nodes whose embedding was produced by a different model.

Run once after changing KNOWLEDGE_EMBEDDING_MODEL in .env (e.g. switching models):

    python scripts/migrate_embeddings.py [--dry-run] [--batch-size 50]

Idempotent: nodes already using the current model are skipped.
Episodic Memory embeddings are managed separately via EMBEDDING_MODEL.
"""

import argparse
import sys

from memory_service.config import Settings, get_driver
from memory_service.embeddings import get_embedding


# Node labels that carry embeddings and the reconstruction strategy for each.
# Text reconstruction is done in _reconstruct_text() below.
# Memory embeddings are managed independently via EMBEDDING_MODEL — not migrated here.
EMBEDDABLE_LABELS = [
    # (label, text_property_or_None)
    # For Control: text = code + " " + title + " " + body
    # For Chunk:   text = heading + " " + body
    ("Control", None),  # special: reconstruct from code + title + body
    ("Chunk", None),    # special: reconstruct from heading + body
]


def _reconstruct_text(label: str, node: dict) -> str | None:
    """Return the text that should be embedded for this node, or None to skip."""
    if label == "Memory":
        fact = (node.get("fact") or "").strip()
        so_what = (node.get("so_what") or "").strip()
        if not fact:
            return None
        return (fact + " " + so_what).strip() if so_what else fact

    if label == "Control":
        code = (node.get("code") or "").strip()
        title = (node.get("title") or "").strip()
        body = (node.get("body") or "").strip()
        text = " ".join(part for part in [code, title, body] if part)
        return text.strip() or None

    if label == "Chunk":
        heading = (node.get("heading") or "").strip()
        body = (node.get("body") or "").strip()
        if not body:
            return None
        text = (heading + " " + body).strip() if heading else body
        return text.strip()

    return None


def _process_label(
    session,
    label: str,
    model_name: str,
    batch_size: int,
    dry_run: bool,
) -> tuple[int, int, int]:
    """Process all stale-model nodes for *label*.

    Returns (updated, skipped, failed) counts.
    """
    updated = 0
    skipped = 0
    failed = 0

    # Fetch nodes whose embedding was made with a different model (or never embedded).
    fetch_query = (
        f"MATCH (n:{label}) "
        f"WHERE n.embedding_model_name <> $model OR n.embedding_model_name IS NULL "
        f"RETURN n"
    )

    result = session.run(fetch_query, model=model_name)
    nodes = [record["n"] for record in result]

    total_stale = len(nodes)
    if total_stale == 0:
        print(f"  {label}: 0 stale nodes — nothing to do.")
        return 0, 0, 0

    print(f"  {label}: {total_stale} stale node(s) to re-embed ...")

    batch: list[tuple[str, list[float]]] = []

    def flush_batch() -> None:
        nonlocal updated
        if not batch or dry_run:
            updated += len(batch)
            return
        update_query = (
            f"MATCH (n:{label} {{id: $node_id}}) "
            f"SET n.embedding = $embedding, n.embedding_model_name = $model_name"
        )
        for node_id, embedding in batch:
            session.run(
                update_query,
                node_id=node_id,
                embedding=embedding,
                model_name=model_name,
            )
        updated += len(batch)

    for node in nodes:
        node_dict = dict(node)
        node_id = node_dict.get("id")
        if not node_id:
            print(f"    [SKIP] {label} node has no 'id' property — skipping.")
            skipped += 1
            continue

        text = _reconstruct_text(label, node_dict)
        if not text:
            print(f"    [SKIP] {label} id={node_id!r} — could not reconstruct text.")
            skipped += 1
            continue

        try:
            embedding = get_embedding(text)
        except Exception as exc:
            print(f"    [FAIL] {label} id={node_id!r} — embedding error: {exc}")
            failed += 1
            continue

        batch.append((node_id, embedding))

        if len(batch) >= batch_size:
            flush_batch()
            batch.clear()
            action = "Would update" if dry_run else "Updated"
            print(f"    {action} {updated} node(s) so far ...")

    if batch:
        flush_batch()
        batch.clear()

    action = "Would update" if dry_run else "Updated"
    print(
        f"  {label}: {action} {updated}, skipped {skipped}, failed {failed} "
        f"(of {total_stale} stale)."
    )
    return updated, skipped, failed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Re-embed nodes whose embedding_model_name differs from the current model."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count stale nodes and generate embeddings but do not write back to the DB.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        metavar="N",
        help="Number of nodes to write per transaction batch (default: 50).",
    )
    args = parser.parse_args()

    settings = Settings()
    model_name = settings.knowledge_embedding_model
    uri = f"bolt://{settings.memgraph_host}:{settings.memgraph_port}"

    print(f"Connecting to Memgraph at {uri} ...")
    try:
        driver = get_driver(settings)
        driver.verify_connectivity()
    except Exception as exc:
        print(f"[FAIL] Could not connect to Memgraph: {exc}")
        return 1

    print(f"Embedding model (knowledge layer): '{model_name}'")
    if args.dry_run:
        print("[DRY RUN] No writes will be made.")
    print(f"Batch size: {args.batch_size}")

    # Warm up the embedding model once before the loop.
    print(f"\nLoading embedding model '{model_name}' ...")
    try:
        # Force model load by generating a trivial embedding.
        get_embedding("warm-up")
    except Exception as exc:
        driver.close()
        print(f"[FAIL] Could not load embedding model '{model_name}': {exc}")
        return 1
    print("  Model loaded.")

    total_updated = 0
    total_skipped = 0
    total_failed = 0

    try:
        with driver.session() as session:
            print("\nMigrating embeddings ...")
            for label, _ in EMBEDDABLE_LABELS:
                print(f"\nProcessing label: {label}")
                try:
                    updated, skipped, failed = _process_label(
                        session,
                        label=label,
                        model_name=model_name,
                        batch_size=args.batch_size,
                        dry_run=args.dry_run,
                    )
                    total_updated += updated
                    total_skipped += skipped
                    total_failed += failed
                except Exception as exc:
                    print(f"  [FAIL] Unhandled error processing label {label}: {exc}")
                    total_failed += 1

    except Exception as exc:
        print(f"[FAIL] Session error: {exc}")
        return 1
    finally:
        driver.close()

    action = "Would update" if args.dry_run else "Updated"
    print(
        f"\nMigration complete. "
        f"{action} {total_updated} node(s), "
        f"skipped {total_skipped}, "
        f"failed {total_failed}."
    )
    return 0 if total_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
