#!/usr/bin/env python3
"""scripts/ingest_attack.py — Ingest MITRE ATT&CK Enterprise into the knowledge layer.

Hierarchy ingested as Framework nodes:
    ATT&CK Enterprise root
    └── Tactic (level: category, external_id: TA0001..TA0043)
        └── Technique (level: technique, external_id: T1001..Txxx)
            └── Sub-technique (level: sub-technique, external_id: T1001.001..)

A technique that spans multiple tactics receives a CONTAINS edge from each tactic,
preserving full kill-chain traversal fidelity.

ID scheme:
    root         → attack-enterprise-v{MAJOR}             e.g. attack-enterprise-v17
    tactic       → attack-enterprise.TA0001
    technique    → attack-enterprise.T1566
    sub-technique → attack-enterprise.T1566.001

Usage:
    python3 scripts/ingest_attack.py
    python3 scripts/ingest_attack.py --stix-file data/frameworks/enterprise-attack-17.0.json
    python3 scripts/ingest_attack.py --dry-run

Reads API_BASE_URL from .env (defaults to http://localhost:8000).
Idempotent: safe to re-run; all writes use MERGE on the API side.
"""
from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path
from typing import Optional

import httpx
from mitreattack.stix20 import MitreAttackData
from pydantic_settings import BaseSettings, SettingsConfigDict

STIX_DOWNLOAD_URL = (
    "https://raw.githubusercontent.com/mitre-attack/attack-stix-data"
    "/master/enterprise-attack/enterprise-attack-17.0.json"
)
DEFAULT_STIX_PATH = Path(__file__).parent.parent / "data" / "frameworks" / "enterprise-attack-17.0.json"
DOMAIN = "enterprise"


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

class ETLSettings(BaseSettings):
    api_base_url: str = "http://localhost:8000"
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_external_id(stix_obj) -> Optional[str]:
    """Return the ATT&CK external ID (e.g. T1566.001) from external_references."""
    for ref in stix_obj.get("external_references", []):
        if ref.get("source_name") == "mitre-attack":
            return ref.get("external_id")
    return None


def _node_id(external_id: str) -> str:
    """Map ATT&CK external ID to our Framework node ID.

    TA0001 → attack-enterprise.TA0001
    T1566  → attack-enterprise.T1566
    T1566.001 → attack-enterprise.T1566.001
    """
    return f"attack-enterprise.{external_id}"


def _root_id(version: str) -> str:
    """Return root node ID from version string like '17.0'."""
    major = version.split(".")[0]
    return f"attack-enterprise-v{major}"


def _upsert(client: httpx.Client, body: dict, label: str, dry_run: bool) -> str:
    """POST /knowledge/frameworks; return 'created', 'already existed', or 'error'."""
    if dry_run:
        return "dry-run"
    try:
        resp = client.post("/knowledge/frameworks", json=body)
        resp.raise_for_status()
        return "created"
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 409:
            return "already existed"
        print(f"  [ERR] {label}: HTTP {exc.response.status_code} — {exc.response.text[:200]}",
              file=sys.stderr)
        return "error"
    except httpx.HTTPError as exc:
        print(f"  [ERR] {label}: {exc}", file=sys.stderr)
        return "error"


def _add_contains(client: httpx.Client, parent_id: str, child_id: str, dry_run: bool) -> str:
    """POST a minimal upsert for the child with parent_id set to create the CONTAINS edge.

    Since ON MATCH only updates statement_type/modality, this is safe to call
    for a node that already exists — it will add the extra CONTAINS edge without
    clobbering other properties.
    """
    if dry_run:
        return "dry-run"
    try:
        # We only need id + title (required) + parent_id to trigger the CONTAINS merge
        resp = client.post("/knowledge/frameworks", json={"id": child_id, "title": child_id, "parent_id": parent_id})
        resp.raise_for_status()
        return "ok"
    except httpx.HTTPStatusError as exc:
        print(f"  [ERR] extra-contains {parent_id}→{child_id}: HTTP {exc.response.status_code}",
              file=sys.stderr)
        return "error"
    except httpx.HTTPError as exc:
        print(f"  [ERR] extra-contains {parent_id}→{child_id}: {exc}", file=sys.stderr)
        return "error"


# ---------------------------------------------------------------------------
# Ingestion steps
# ---------------------------------------------------------------------------

def ingest_root(client: httpx.Client, version: str, dry_run: bool) -> str:
    """Create the ATT&CK Enterprise root Framework node."""
    root = _root_id(version)
    body = {
        "id": root,
        "title": "MITRE ATT&CK Enterprise",
        "version": version,
        "level": "framework",
        "domain": DOMAIN,
        "body": (
            "MITRE ATT&CK is a globally-accessible knowledge base of adversary tactics "
            "and techniques based on real-world observations. The ATT&CK knowledge base "
            "is used as a foundation for the development of specific threat models and "
            "methodologies in the private sector, in government, and in the cybersecurity "
            "product and service community."
        ),
    }
    status = _upsert(client, body, f"root/{root}", dry_run)
    print(f"  Root {root}: {status}")
    return root


def ingest_tactics(
    client: httpx.Client,
    data: MitreAttackData,
    root_id: str,
    dry_run: bool,
) -> dict[str, str]:
    """Create Tactic nodes (CONTAINS from root). Returns {shortname: node_id} mapping."""
    tactics = data.get_tactics(remove_revoked_deprecated=True)
    shortname_to_id: dict[str, str] = {}
    ok = 0

    for tactic in tactics:
        ext_id = _get_external_id(tactic)
        if not ext_id:
            continue
        node_id = _node_id(ext_id)
        shortname = tactic.get("x_mitre_shortname", "")
        shortname_to_id[shortname] = node_id

        desc = tactic.get("description", "")
        # Strip markdown link clutter from ATT&CK descriptions
        desc_clean = desc.split("\n")[0].strip() if desc else None

        body = {
            "id": node_id,
            "title": tactic["name"],
            "level": "category",
            "external_id": ext_id,
            "domain": DOMAIN,
            "parent_id": root_id,
        }
        if desc_clean:
            body["body"] = desc_clean

        status = _upsert(client, body, f"tactic/{ext_id}", dry_run)
        if status not in ("error",):
            ok += 1

    print(f"  Tactics: {ok}/{len(tactics)} upserted")
    return shortname_to_id


def ingest_techniques(
    client: httpx.Client,
    data: MitreAttackData,
    shortname_to_tactic_id: dict[str, str],
    dry_run: bool,
) -> None:
    """Create Technique nodes (CONTAINS from all parent tactics)."""
    techniques = data.get_techniques(
        remove_revoked_deprecated=True,
        include_subtechniques=False,
    )
    ok = 0
    extra_edges = 0

    for tech in techniques:
        ext_id = _get_external_id(tech)
        if not ext_id:
            continue
        node_id = _node_id(ext_id)

        kill_chain_phases = [
            kc["phase_name"]
            for kc in tech.get("kill_chain_phases", [])
            if kc.get("kill_chain_name") == "mitre-attack"
        ]
        tactic_node_ids = [
            shortname_to_tactic_id[phase]
            for phase in kill_chain_phases
            if phase in shortname_to_tactic_id
        ]

        desc = tech.get("description", "")
        # First paragraph only — descriptions can be very long
        first_para = desc.split("\n\n")[0].strip() if desc else None

        body = {
            "id": node_id,
            "title": tech["name"],
            "level": "technique",
            "external_id": ext_id,
            "domain": DOMAIN,
        }
        if first_para:
            body["body"] = first_para[:2000]  # cap at 2000 chars for embedding quality
        if tactic_node_ids:
            body["parent_id"] = tactic_node_ids[0]  # primary tactic

        status = _upsert(client, body, f"technique/{ext_id}", dry_run)
        if status not in ("error",):
            ok += 1

        # Extra CONTAINS edges for multi-tactic techniques
        for extra_tactic_id in tactic_node_ids[1:]:
            _add_contains(client, extra_tactic_id, node_id, dry_run)
            extra_edges += 1

    print(f"  Techniques: {ok}/{len(techniques)} upserted, {extra_edges} extra tactic edges")


def ingest_subtechniques(
    client: httpx.Client,
    data: MitreAttackData,
    dry_run: bool,
) -> None:
    """Create Sub-technique nodes (CONTAINS from parent technique)."""
    all_techniques = data.get_techniques(
        remove_revoked_deprecated=True,
        include_subtechniques=True,
    )
    subtechniques = [t for t in all_techniques if t.get("x_mitre_is_subtechnique", False)]
    ok = 0

    for sub in subtechniques:
        ext_id = _get_external_id(sub)
        if not ext_id:
            continue
        node_id = _node_id(ext_id)

        # Derive parent technique ID from external_id (T1566.001 → T1566)
        parent_ext_id = ext_id.rsplit(".", 1)[0]
        parent_node_id = _node_id(parent_ext_id)

        desc = sub.get("description", "")
        first_para = desc.split("\n\n")[0].strip() if desc else None

        body = {
            "id": node_id,
            "title": sub["name"],
            "level": "sub-technique",
            "external_id": ext_id,
            "domain": DOMAIN,
            "parent_id": parent_node_id,
        }
        if first_para:
            body["body"] = first_para[:2000]

        status = _upsert(client, body, f"sub-technique/{ext_id}", dry_run)
        if status not in ("error",):
            ok += 1

    print(f"  Sub-techniques: {ok}/{len(subtechniques)} upserted")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--stix-file",
        default=None,
        help="Path to local STIX 2.1 JSON bundle. Downloads if not provided.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse STIX and report counts without making any API calls.",
    )
    return parser.parse_args()


def _resolve_stix_path(stix_file: Optional[str]) -> Path:
    """Return path to STIX file, downloading if necessary."""
    if stix_file:
        path = Path(stix_file)
        if not path.exists():
            print(f"Error: STIX file not found: {path}", file=sys.stderr)
            sys.exit(1)
        return path

    if DEFAULT_STIX_PATH.exists():
        print(f"Using cached STIX bundle: {DEFAULT_STIX_PATH}")
        return DEFAULT_STIX_PATH

    print(f"Downloading ATT&CK Enterprise STIX bundle from MITRE GitHub...")
    DEFAULT_STIX_PATH.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(STIX_DOWNLOAD_URL, DEFAULT_STIX_PATH)
    print(f"Saved to: {DEFAULT_STIX_PATH}")
    return DEFAULT_STIX_PATH


def main() -> None:
    args = _parse_args()
    cfg = ETLSettings()

    stix_path = _resolve_stix_path(args.stix_file)

    print(f"Loading STIX bundle: {stix_path.name}")
    data = MitreAttackData(str(stix_path))

    # Determine version from bundle metadata
    collections = data.get_objects_by_type("x-mitre-collection")
    version = collections[0].get("x_mitre_version", "17.0") if collections else "17.0"
    root = _root_id(version)
    print(f"ATT&CK Enterprise version: {version}  (root id: {root})")

    techniques = data.get_techniques(remove_revoked_deprecated=True, include_subtechniques=False)
    all_techniques = data.get_techniques(remove_revoked_deprecated=True, include_subtechniques=True)
    subtechniques = [t for t in all_techniques if t.get("x_mitre_is_subtechnique", False)]
    tactics = data.get_tactics(remove_revoked_deprecated=True)

    total = 1 + len(tactics) + len(techniques) + len(subtechniques)
    print(f"Nodes to ingest: {total} total")
    print(f"  1 root + {len(tactics)} tactics + {len(techniques)} techniques + {len(subtechniques)} sub-techniques")

    if args.dry_run:
        print("\nDry run: no API calls made.")
        return

    print()
    with httpx.Client(base_url=cfg.api_base_url, timeout=60.0) as client:
        ingest_root(client, version, dry_run=False)
        shortname_to_tactic_id = ingest_tactics(client, data, root, dry_run=False)
        ingest_techniques(client, data, shortname_to_tactic_id, dry_run=False)
        ingest_subtechniques(client, data, dry_run=False)

    print(f"\nDone: ATT&CK Enterprise v{version} ingested ({total} nodes)")


if __name__ == "__main__":
    main()
