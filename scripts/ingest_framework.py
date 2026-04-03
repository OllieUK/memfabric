#!/usr/bin/env python3
"""Bulk-ingest a framework YAML catalogue into the knowledge layer.

Usage:
    python scripts/ingest_framework.py <yaml_file> [--dry-run]

Reads config from .env (API_BASE_URL). Validates the YAML against the
YamlFrameworkFile schema before making any HTTP calls. Upserts in dependency
order: Framework → Controls → Norms → Documents → Chunks → Jurisdictions →
BusinessAttributes. Idempotent: re-running the same file is safe.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

import httpx
import yaml
from pydantic import BaseModel, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

class ETLSettings(BaseSettings):
    api_base_url: str = "http://localhost:8000"
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


# ---------------------------------------------------------------------------
# YAML schema models
# ---------------------------------------------------------------------------

class YamlControl(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    parent_id: Optional[str] = None


class YamlNorm(BaseModel):
    id: str
    name: str
    text: str
    status: str = "active"
    effective_date: Optional[str] = None
    control_id: Optional[str] = None


class YamlDocument(BaseModel):
    id: str
    title: str
    doc_type: str
    source_url: Optional[str] = None


class YamlChunk(BaseModel):
    id: str
    text: str
    sequence: int
    doc_id: str
    prev_chunk_id: Optional[str] = None


class YamlJurisdiction(BaseModel):
    id: str
    name: str
    region: Optional[str] = None


class YamlBusinessAttribute(BaseModel):
    id: str
    name: str
    description: Optional[str] = None


class YamlFrameworkFile(BaseModel):
    framework_id: str
    framework_name: str
    framework_version: Optional[str] = None
    framework_description: Optional[str] = None
    controls: list[YamlControl] = []
    norms: list[YamlNorm] = []
    documents: list[YamlDocument] = []
    chunks: list[YamlChunk] = []
    jurisdictions: list[YamlJurisdiction] = []
    business_attributes: list[YamlBusinessAttribute] = []


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _upsert(client: httpx.Client, endpoint: str, body: dict, label: str) -> str:
    """POST to endpoint; return 'created' or 'already existed' based on response."""
    try:
        resp = client.post(endpoint, json=body)
        resp.raise_for_status()
        return "created"
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 409:
            return "already existed"
        print(f"  [ERR] {label}: HTTP {exc.response.status_code} — {exc.response.text}", file=sys.stderr)
        return "error"
    except httpx.HTTPError as exc:
        print(f"  [ERR] {label}: {exc}", file=sys.stderr)
        return "error"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("yaml_file", help="Path to the framework YAML file")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the YAML and print what would be ingested, but make no API calls",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    cfg = ETLSettings()

    yaml_path = Path(args.yaml_file)
    if not yaml_path.exists():
        print(f"Error: file not found: {yaml_path}", file=sys.stderr)
        sys.exit(1)

    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    try:
        fw = YamlFrameworkFile.model_validate(raw)
    except ValidationError as exc:
        print(f"Validation error in {yaml_path}:\n{exc}", file=sys.stderr)
        sys.exit(1)

    total = (
        1  # framework node itself
        + len(fw.controls)
        + len(fw.norms)
        + len(fw.documents)
        + len(fw.chunks)
        + len(fw.jurisdictions)
        + len(fw.business_attributes)
    )
    print(f"Validated: {yaml_path.name} — {total} items")
    print(f"  Framework: {fw.framework_id} ({fw.framework_name})")
    print(f"  Controls: {len(fw.controls)}, Norms: {len(fw.norms)}, Documents: {len(fw.documents)}")
    print(f"  Chunks: {len(fw.chunks)}, Jurisdictions: {len(fw.jurisdictions)}, BusinessAttributes: {len(fw.business_attributes)}")

    if args.dry_run:
        print("\nDry run: no API calls made.")
        return

    with httpx.Client(base_url=cfg.api_base_url) as client:
        # 1. Framework
        status = _upsert(
            client,
            "/knowledge/frameworks",
            {
                "id": fw.framework_id,
                "name": fw.framework_name,
                "version": fw.framework_version,
                "description": fw.framework_description,
            },
            f"framework/{fw.framework_id}",
        )
        print(f"  Framework {fw.framework_id}: {status}")

        # 2. Controls (upsert in order — parent before child if parent_id used)
        ctrl_ok = 0
        for ctrl in fw.controls:
            body: dict = {
                "id": ctrl.id,
                "name": ctrl.name,
                "framework_id": fw.framework_id,
            }
            if ctrl.description is not None:
                body["description"] = ctrl.description
            if ctrl.parent_id is not None:
                body["parent_id"] = ctrl.parent_id
            s = _upsert(client, "/knowledge/controls", body, f"control/{ctrl.id}")
            if s != "error":
                ctrl_ok += 1
        print(f"  Controls: {ctrl_ok}/{len(fw.controls)} upserted")

        # 3. Norms
        norm_ok = 0
        for norm in fw.norms:
            body = {
                "id": norm.id,
                "name": norm.name,
                "text": norm.text,
                "status": norm.status,
            }
            if norm.effective_date is not None:
                body["effective_date"] = norm.effective_date
            if norm.control_id is not None:
                body["control_id"] = norm.control_id
            s = _upsert(client, "/knowledge/norms", body, f"norm/{norm.id}")
            if s != "error":
                norm_ok += 1
        print(f"  Norms: {norm_ok}/{len(fw.norms)} upserted")

        # 4. Documents
        doc_ok = 0
        for doc in fw.documents:
            body = {"id": doc.id, "title": doc.title, "doc_type": doc.doc_type}
            if doc.source_url is not None:
                body["source_url"] = doc.source_url
            s = _upsert(client, "/knowledge/documents", body, f"document/{doc.id}")
            if s != "error":
                doc_ok += 1
        print(f"  Documents: {doc_ok}/{len(fw.documents)} upserted")

        # 5. Chunks
        chunk_ok = 0
        for chunk in fw.chunks:
            body = {
                "id": chunk.id,
                "text": chunk.text,
                "sequence": chunk.sequence,
                "doc_id": chunk.doc_id,
            }
            if chunk.prev_chunk_id is not None:
                body["prev_chunk_id"] = chunk.prev_chunk_id
            s = _upsert(client, "/knowledge/chunks", body, f"chunk/{chunk.id}")
            if s != "error":
                chunk_ok += 1
        print(f"  Chunks: {chunk_ok}/{len(fw.chunks)} upserted")

        # 6. Jurisdictions (POST to /knowledge/jurisdictions if it exists; log skip if 404)
        jur_ok = 0
        for jur in fw.jurisdictions:
            body = {"id": jur.id, "name": jur.name}
            if jur.region is not None:
                body["region"] = jur.region
            s = _upsert(client, "/knowledge/jurisdictions", body, f"jurisdiction/{jur.id}")
            if s != "error":
                jur_ok += 1
        if fw.jurisdictions:
            print(f"  Jurisdictions: {jur_ok}/{len(fw.jurisdictions)} upserted")

        # 7. BusinessAttributes
        ba_ok = 0
        for ba in fw.business_attributes:
            body = {"id": ba.id, "name": ba.name}
            if ba.description is not None:
                body["description"] = ba.description
            s = _upsert(client, "/knowledge/business-attributes", body, f"business-attribute/{ba.id}")
            if s != "error":
                ba_ok += 1
        if fw.business_attributes:
            print(f"  BusinessAttributes: {ba_ok}/{len(fw.business_attributes)} upserted")

    print(f"\nDone: {fw.framework_id}")


if __name__ == "__main__":
    main()
