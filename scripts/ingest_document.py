#!/usr/bin/env python3
"""Ingest a PDF or Markdown document into the knowledge layer.

Usage:
    python scripts/ingest_document.py <file_path> \
        --doc-id <id> --title <title> --doc-type <policy|procedure|standard|guideline> \
        [--source-url <url>]

Reads config from .env (API_BASE_URL, INGEST_* settings).
"""
import argparse
import sys
import uuid
from pathlib import Path

import httpx
from pydantic_settings import BaseSettings, SettingsConfigDict


class IngestSettings(BaseSettings):
    api_base_url: str = "http://localhost:8000"
    knowledge_embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    ingest_chunk_size: int = 2000
    ingest_chunk_overlap: int = 200
    ingest_min_chunk_chars: int = 50
    ingest_auto_supports: bool = False
    ingest_auto_supports_threshold: float = 0.20
    ingest_chunk_review_mode: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("file_path", help="Path to the PDF or Markdown file to ingest")
    parser.add_argument("--doc-id", required=True, help="Unique document ID")
    parser.add_argument("--title", required=True, help="Document title")
    parser.add_argument(
        "--doc-type",
        required=True,
        choices=["policy", "procedure", "standard", "guideline"],
        help="Document type",
    )
    parser.add_argument("--source-url", default=None, help="Optional source URL")
    return parser.parse_args()


def _ingest_document(
    client: httpx.Client,
    doc_id: str,
    title: str,
    doc_type: str,
    source_url: str | None,
) -> dict:
    body: dict = {"id": doc_id, "title": title, "doc_type": doc_type}
    if source_url:
        body["source_url"] = source_url
    resp = client.post("/knowledge/documents", json=body)
    resp.raise_for_status()
    return resp.json()


def _post_chunk(
    client: httpx.Client,
    chunk_id: str,
    doc_id: str,
    text: str,
    sequence: int,
    prev_chunk_id: str | None,
) -> dict:
    body: dict = {
        "id": chunk_id,
        "doc_id": doc_id,
        "text": text,
        "sequence": sequence,
    }
    if prev_chunk_id is not None:
        body["prev_chunk_id"] = prev_chunk_id
    resp = client.post("/knowledge/chunks", json=body)
    resp.raise_for_status()
    return resp.json()


def _search_controls(client: httpx.Client, query: str, limit: int = 3) -> list[dict]:
    resp = client.post("/knowledge/search/controls", json={"query": query, "limit": limit})
    resp.raise_for_status()
    return resp.json()


def _post_supports(
    client: httpx.Client,
    chunk_id: str,
    control_id: str,
    confidence: float,
) -> dict:
    resp = client.post(
        "/knowledge/chunks/supports",
        json={
            "chunk_id": chunk_id,
            "control_id": control_id,
            "confidence": confidence,
            "status": "auto-inferred",
        },
    )
    resp.raise_for_status()
    return resp.json()


def main() -> None:
    args = _parse_args()
    cfg = IngestSettings()

    file_path = Path(args.file_path)
    if not file_path.exists():
        print(f"Error: file not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        from scripts.chunkers import chunk_pdf
        chunks = chunk_pdf(
            str(file_path),
            cfg.ingest_chunk_size,
            cfg.ingest_chunk_overlap,
            cfg.ingest_min_chunk_chars,
        )
    elif suffix in (".md", ".markdown"):
        from scripts.chunkers import chunk_markdown
        chunks = chunk_markdown(
            file_path.read_text(encoding="utf-8"),
            cfg.ingest_min_chunk_chars,
        )
    else:
        print(
            f"Error: unsupported file type '{suffix}'. Supported: .pdf, .md, .markdown",
            file=sys.stderr,
        )
        sys.exit(1)

    with httpx.Client(base_url=cfg.api_base_url) as client:
        try:
            _ingest_document(client, args.doc_id, args.title, args.doc_type, args.source_url)
            print(f"Document: {args.doc_id} ({args.title})")
        except httpx.HTTPError as exc:
            print(f"Error: failed to create document: {exc}", file=sys.stderr)
            sys.exit(1)

        chunk_ids: list[str | None] = []
        chunk_texts: list[str] = []
        prev_chunk_id: str | None = None

        for chunk in chunks:
            chunk_id = str(uuid.uuid4())
            try:
                _post_chunk(client, chunk_id, args.doc_id, chunk.text, chunk.sequence, prev_chunk_id)
                chunk_ids.append(chunk_id)
                chunk_texts.append(chunk.text)
                prev_chunk_id = chunk_id
                print(f"  [OK] chunk {chunk.sequence}: {len(chunk.text)} chars")
            except httpx.HTTPError as exc:
                print(f"  [ERR] chunk {chunk.sequence}: {exc}", file=sys.stderr)
                chunk_ids.append(None)
                chunk_texts.append(chunk.text)
                prev_chunk_id = None

        if cfg.ingest_auto_supports:
            candidates: list[dict] = []
            for cid, ctext in zip(chunk_ids, chunk_texts):
                if cid is None:
                    continue
                try:
                    hits = _search_controls(client, ctext)
                    for hit in hits:
                        if hit["distance"] < cfg.ingest_auto_supports_threshold:
                            candidates.append({
                                "chunk_id": cid,
                                "control_id": hit["id"],
                                "confidence": round(1.0 - hit["distance"], 4),
                            })
                except httpx.HTTPError as exc:
                    print(f"  [WARN] control search failed for chunk {cid}: {exc}", file=sys.stderr)

            if cfg.ingest_chunk_review_mode:
                print(f"\nSUPPORTS candidates ({len(candidates)} found):")
                print(f"{'chunk_id':<36}  {'control_id':<36}  confidence")
                print("-" * 80)
                for c in candidates:
                    print(f"{c['chunk_id']:<36}  {c['control_id']:<36}  {c['confidence']:.4f}")
                print(
                    "\nReview mode: no SUPPORTS edges created. "
                    "Set INGEST_CHUNK_REVIEW_MODE=false to apply."
                )
            else:
                created = 0
                for c in candidates:
                    try:
                        _post_supports(client, c["chunk_id"], c["control_id"], c["confidence"])
                        created += 1
                    except httpx.HTTPError as exc:
                        print(f"  [WARN] SUPPORTS edge failed {c['chunk_id']}→{c['control_id']}: {exc}", file=sys.stderr)
                print(f"Created {created} SUPPORTS edges (status=auto-inferred)")

    successful = len([c for c in chunk_ids if c is not None])
    print(f"\nIngested: {args.doc_id} | {successful} chunks")


if __name__ == "__main__":
    main()
