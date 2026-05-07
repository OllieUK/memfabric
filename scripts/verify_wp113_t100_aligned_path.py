#!/usr/bin/env python3
"""
scripts/verify_wp113_t100_aligned_path.py — WP-113 acceptance gate verification.

Verifies that the T100-aligned strategic threat-to-business traversal path is
operational in the production knowledge graph. Checks all acceptance criteria
for WP-113 and prints a summary gate report.

Strategic path under test:
    Threat -[INFLUENCE]-> BusinessAttribute
    Framework -[INFORMS]-> BusinessAttribute

Usage:
    python scripts/verify_wp113_t100_aligned_path.py
    python scripts/verify_wp113_t100_aligned_path.py --api-url https://memfabric.carr-it.net
    python scripts/verify_wp113_t100_aligned_path.py --verbose
"""

import argparse
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.script_utils import get_api_client, make_settings, search_threats

_BA_ENDPOINT = "/knowledge/business-attributes"
_FRAMEWORK_ENDPOINT = "/knowledge/frameworks"

_EXPECTED_PRIMITIVE_ROOTS = 8
_EXPECTED_DEPRECATED = 3
_EXPECTED_ICT_LEAF_MIN = 80
_EXPECTED_INFORMS_GROUPS_MIN = 6
_EXPECTED_ICT_GROUPS_TOTAL = 7

# One cell per layer — confirm the main-matrix seeding is intact
_SABSA_CELL_PROBE_IDS = [
    "sabsa-2018.matrix-main.contextual.assets",
    "sabsa-2018.matrix-main.conceptual.motivation",
    "sabsa-2018.matrix-main.logical.assets",
    "sabsa-2018.matrix-main.physical.process",
    "sabsa-2018.matrix-main.component.people",
    "sabsa-2018.matrix-main.operational.time",
]


def _count_sabsa_cells(client) -> tuple[int, int]:
    found = sum(
        1 for cell_id in _SABSA_CELL_PROBE_IDS
        if client.get(f"{_FRAMEWORK_ENDPOINT}/{cell_id}").status_code == 200
    )
    return found, len(_SABSA_CELL_PROBE_IDS)


def _check_influence_path(client, ict_leaves: list[dict]) -> tuple[bool, str]:
    """Confirm the threat embedding index is populated and returns results for BA vocabulary.

    The API has no INFLUENCE edge listing endpoint. We verify the path is operational
    by confirming threat search returns hits for a security-oriented BA name — the same
    mechanism that produced the 183 INFLUENCE edges during Phase 7.
    """
    test_ba = next((b for b in ict_leaves if "confidential" in b["id"]), ict_leaves[0] if ict_leaves else None)
    if not test_ba:
        return False, "No ICT-leaf BAs found to probe"
    hits = search_threats(client, test_ba["name"], 3)
    if not hits:
        return False, f"Threat search for '{test_ba['name']}' returned no hits"
    return True, f"Threat search for '{test_ba['name']}' returned {len(hits)} hits (confirms embedding path active)"


def _check_framework_informs(client, ict_leaves: list[dict], verbose: bool) -> tuple[int, list[str]]:
    """Return (covered_group_count, gap_list) for Framework→BA INFORMS coverage.

    Probing framework search rather than directly counting INFORMS edges because
    there is no list endpoint for edges. A framework search hit for a BA name
    confirms the embedding index that drives INFORMS wiring is functional.
    """
    all_groups = sorted({b.get("group", "ungrouped") for b in ict_leaves})
    covered = set()
    for g in all_groups:
        group_bas = [b for b in ict_leaves if b.get("group") == g]
        for ba in group_bas[:3]:
            resp = client.post("/knowledge/search/frameworks", json={"query": ba["name"], "limit": 5})
            if resp.status_code == 200 and resp.json():
                covered.add(g)
                break
    gaps = [g for g in all_groups if g not in covered]
    if verbose:
        for g in all_groups:
            print(f"    {'✓' if g in covered else '✗'} {g}")
    return len(covered), gaps


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify WP-113 T100-aligned strategic path acceptance criteria"
    )
    parser.add_argument("--api-url", help="Override API base URL")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show per-group detail")
    args = parser.parse_args()

    results: list[tuple[str, bool, str]] = []

    with get_api_client(make_settings(args.api_url)) as client:
        # ── Gate 1: Health check ───────────────────────────────────────────
        resp = client.get("/health")
        results.append(("API health", resp.status_code == 200, f"HTTP {resp.status_code}"))

        # ── Fetch all BAs once; slice into tiers for remaining gates ───────
        all_ba_resp = client.get(f"{_BA_ENDPOINT}?limit=500&include_deprecated=true")
        all_ba_resp.raise_for_status()
        all_ba = all_ba_resp.json()

        deprecated = [b for b in all_ba if b.get("status") == "deprecated"]
        active = [b for b in all_ba if b.get("status") == "active"]
        primitive_roots = [b for b in active if b.get("tier") == "primitive-root"]
        ict_leaves = [b for b in active if b.get("tier") == "ict-leaf"]

        # ── Gate 2: BusinessAttribute taxonomy ────────────────────────────
        results.append((
            f"Primitive-root BAs (≥{_EXPECTED_PRIMITIVE_ROOTS})",
            len(primitive_roots) >= _EXPECTED_PRIMITIVE_ROOTS,
            f"{len(primitive_roots)} found",
        ))
        results.append((
            f"Deprecated BA tombstones (≥{_EXPECTED_DEPRECATED})",
            len(deprecated) >= _EXPECTED_DEPRECATED,
            f"{len(deprecated)} found",
        ))
        results.append((
            f"ICT-leaf BAs (≥{_EXPECTED_ICT_LEAF_MIN})",
            len(ict_leaves) >= _EXPECTED_ICT_LEAF_MIN,
            f"{len(ict_leaves)} found",
        ))

        # ── Gate 3: ICT group count ────────────────────────────────────────
        groups = sorted({b.get("group") for b in ict_leaves if b.get("group")})
        results.append((
            f"W100 ICT groups (≥{_EXPECTED_ICT_GROUPS_TOTAL})",
            len(groups) >= _EXPECTED_ICT_GROUPS_TOTAL,
            f"{len(groups)} groups: {', '.join(groups)}",
        ))

        # ── Gate 4: SABSA cells (spot-check via known cell IDs) ───────────
        found_cells, probed_cells = _count_sabsa_cells(client)
        results.append((
            f"SABSA matrix cells (spot-check: {probed_cells} known cell IDs)",
            found_cells == probed_cells,
            f"{found_cells}/{probed_cells} cell IDs resolve correctly",
        ))

        # ── Gate 5: Framework→BA INFORMS wiring ───────────────────────────
        if args.verbose:
            print("\nFramework→BA INFORMS coverage by ICT group:")
        covered_groups, gap_groups = _check_framework_informs(client, ict_leaves, args.verbose)
        gap_str = f" (gaps: {', '.join(gap_groups)})" if gap_groups else ""
        results.append((
            f"Framework→BA INFORMS group coverage (≥{_EXPECTED_INFORMS_GROUPS_MIN}/{_EXPECTED_ICT_GROUPS_TOTAL})",
            covered_groups >= _EXPECTED_INFORMS_GROUPS_MIN,
            f"{covered_groups}/{_EXPECTED_ICT_GROUPS_TOTAL} groups{gap_str}",
        ))

        # ── Gate 6: Threat→BA INFLUENCE embedding path active ─────────────
        influence_ok, influence_msg = _check_influence_path(client, ict_leaves)
        results.append(("Threat→BA INFLUENCE embedding path", influence_ok, influence_msg))

        # ── Gate 7: Strategic path traversal (end-to-end) ─────────────────
        test_query = "access control"
        threat_resp = client.post("/knowledge/search/threats", json={"query": test_query, "limit": 3})
        fw_resp = client.post("/knowledge/search/frameworks", json={"query": test_query, "limit": 3})
        strategic_ok = (
            threat_resp.status_code == 200
            and fw_resp.status_code == 200
            and len(threat_resp.json()) > 0
            and len(fw_resp.json()) > 0
        )
        results.append((
            "Strategic path (Threat + Framework both searchable)",
            strategic_ok,
            f"threats={len(threat_resp.json()) if threat_resp.status_code == 200 else 'err'}, "
            f"frameworks={len(fw_resp.json()) if fw_resp.status_code == 200 else 'err'}",
        ))

    # ── Print gate report ─────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("WP-113 ACCEPTANCE GATE REPORT — T100-aligned strategic path")
    print("=" * 70)

    all_pass = True
    for name, ok, detail in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
        print(f"         {detail}")
        if not ok:
            all_pass = False

    print()
    print(f"Overall: {'ALL GATES PASS ✓' if all_pass else 'ONE OR MORE GATES FAILED ✗'}")
    print("=" * 70)

    if not all_pass:
        sys.exit(1)


if __name__ == "__main__":
    main()
