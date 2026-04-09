#!/usr/bin/env python3
"""create_iso22301_nist_rc_crosswalk.py — Structured INFORMS edges: ISO 22301 → NIST CSF RC.

Adds authoritative crosswalk edges between ISO 22301:2019 clauses and NIST CSF 2.0
Recover (RC) subcategories based on the NIST SP 800-34 / ISO 22301 alignment guidance
and the NIST CSF 2.0 informative references.

Embedding similarity (create_new_framework_informs.py) missed these because BCM vocabulary
("continuity", "resumption", "RTO") and NIST RC phrasing ("restore", "recovery plan")
are paraphrase-level synonyms that fall below the cosine similarity threshold.

All edges use source='structured-crosswalk' and similarity=1.0 to distinguish them from
embedding-derived edges and to give them full traversal weight.

Usage:
    python3 -m scripts.create_iso22301_nist_rc_crosswalk [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from neo4j import GraphDatabase
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    memgraph_host: str = "localhost"
    memgraph_port: int = 7687
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


# ---------------------------------------------------------------------------
# Structured crosswalk — ISO 22301:2019 clause → NIST CSF 2.0 RC subcategory
#
# Mapping rationale (per NIST SP 800-34 Rev 1, NIST CSF 2.0 informative refs,
# and ISO 22301:2019 Annex B informative cross-reference to ISO 31000):
#
# RC.RP — Recovery Plan Execution
#   RC.RP-01: Recovery plan initiated → ISO 22301 clause 8.4 (establishing BC plans)
#   RC.RP-02: Recovery actions prioritised → ISO 22301 8.4.2 (BCM procedures)
#   RC.RP-03: Backup integrity verified → ISO 22301 8.5 (exercising BC plans)
#   RC.RP-04: Post-incident operating norms → ISO 22301 6.1.2 (risks/opportunities),
#              8.2.3 (BIA risk assessment), 8.3.3 (recovery time objectives)
#   RC.RP-05: Systems restored, normal status confirmed → ISO 22301 8.4.2, 8.4.4
#   RC.RP-06: Incident recovery declared, docs completed → ISO 22301 10 (evaluation),
#              8.4.3 (warning & communication)
#
# RC.CO — Recovery Communication
#   RC.CO-03: Recovery comms to stakeholders → ISO 22301 8.4.3 (warning & communication)
#   RC.CO-04: Public updates on incident recovery → ISO 22301 8.4.3
# ---------------------------------------------------------------------------

_CROSSWALK: list[tuple[str, str, str]] = [
    # (iso_22301_id, nist_rc_id, rationale_note)

    # RC.RP-01: Recovery plan execution initiated
    ("iso-22301-2019.8.4",          "nist-csf-2.0.rc.rp-01", "BC plans (8.4) govern recovery plan execution initiation"),
    ("iso-22301-2019.8.4.2",        "nist-csf-2.0.rc.rp-01", "BCM procedures (8.4.2) define how recovery is initiated"),
    ("iso-22301-2019.8.1",          "nist-csf-2.0.rc.rp-01", "Operational control (8.1) covers plan-do-check-act for recovery"),

    # RC.RP-02: Recovery actions selected, scoped, prioritised
    ("iso-22301-2019.8.4.2",        "nist-csf-2.0.rc.rp-02", "BCM procedures (8.4.2) define prioritised recovery actions"),
    ("iso-22301-2019.8.3.3",        "nist-csf-2.0.rc.rp-02", "RTO/RPO (8.3.3) establish recovery priorities and scope"),
    ("iso-22301-2019.8.3.2",        "nist-csf-2.0.rc.rp-02", "BIA (8.3.2) determines which capabilities to restore first"),

    # RC.RP-03: Backup integrity verified before restoration
    ("iso-22301-2019.8.5",          "nist-csf-2.0.rc.rp-03", "BC plan exercising (8.5) includes verifying restoration assets"),
    ("iso-22301-2019.8.6",          "nist-csf-2.0.rc.rp-03", "Evaluation of BC documentation (8.6) covers restoration verification"),

    # RC.RP-04: Critical mission functions considered for post-incident norms
    ("iso-22301-2019.8.2.3.a",      "nist-csf-2.0.rc.rp-04", "Disruption risk assessment (8.2.3.a) establishes post-incident operating norms"),
    ("iso-22301-2019.8.3.3",        "nist-csf-2.0.rc.rp-04", "RTO/MBCO (8.3.3) define minimum acceptable operating levels post-incident"),
    ("iso-22301-2019.6.1.2",        "nist-csf-2.0.rc.rp-04", "Risks and opportunities (6.1.2) informs post-incident risk posture"),
    ("iso-22301-2019.8.3",          "nist-csf-2.0.rc.rp-04", "Business impact analysis process (8.3) defines critical mission dependencies"),

    # RC.RP-05: Systems restored, normal operating status confirmed
    ("iso-22301-2019.8.4.2",        "nist-csf-2.0.rc.rp-05", "BCM procedures (8.4.2) include restoration and return to normal operations"),
    ("iso-22301-2019.8.4.4",        "nist-csf-2.0.rc.rp-05", "Resumption of normal operations (8.4.4) directly maps to RC.RP-05"),
    ("iso-22301-2019.8.5",          "nist-csf-2.0.rc.rp-05", "BC exercising (8.5) confirms restoration works correctly"),

    # RC.RP-06: End of recovery declared, documentation completed
    ("iso-22301-2019.10",           "nist-csf-2.0.rc.rp-06", "Performance evaluation (10) triggers improvement cycle at end of incident"),
    ("iso-22301-2019.8.4.3",        "nist-csf-2.0.rc.rp-06", "Warning & communication (8.4.3) includes declaration of incident end"),
    ("iso-22301-2019.7.5",          "nist-csf-2.0.rc.rp-06", "Documented information (7.5) covers incident-related documentation completion"),

    # RC.CO-03: Recovery comms to internal/external stakeholders
    ("iso-22301-2019.8.4.3",        "nist-csf-2.0.rc.co-03", "Warning & communication procedures (8.4.3) map directly to RC.CO-03"),
    ("iso-22301-2019.8.4.3.block-1.b", "nist-csf-2.0.rc.co-03", "Communication procedures for stakeholders (8.4.3.b) ≡ RC.CO-03"),
    ("iso-22301-2019.7.4",          "nist-csf-2.0.rc.co-03", "Communication planning (7.4) governs who communicates what during recovery"),

    # RC.CO-04: Public updates on incident recovery
    ("iso-22301-2019.8.4.3",        "nist-csf-2.0.rc.co-04", "Warning & communication (8.4.3) includes external/public communication"),
    ("iso-22301-2019.7.4",          "nist-csf-2.0.rc.co-04", "Communication procedures (7.4) define approved external communication channels"),
]


_MERGE_CYPHER = (
    "MATCH (src:Framework {id: $src_id}), (dst:Framework {id: $dst_id}) "
    "MERGE (src)-[r:INFORMS]->(dst) "
    "ON CREATE SET r.source = 'structured-crosswalk', "
    "              r.similarity = 1.0, "
    "              r.note = $note, "
    "              r.created_at = $now "
    "RETURN type(r) AS rel_type"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Print edges without writing")
    args = parser.parse_args()

    cfg = Settings()
    driver = GraphDatabase.driver(
        f"bolt://{cfg.memgraph_host}:{cfg.memgraph_port}", auth=("", "")
    )
    now = datetime.now(timezone.utc).isoformat()

    created = skipped = errors = 0

    try:
        with driver.session() as session:
            # Verify both frameworks exist
            for fw_prefix, name in [("iso-22301-2019.", "ISO 22301"), ("nist-csf-2.0.rc.", "NIST CSF RC")]:
                r = session.run(
                    "MATCH (f:Framework) WHERE f.id STARTS WITH $p RETURN count(f) AS cnt",
                    p=fw_prefix,
                )
                cnt = r.single()["cnt"]
                if cnt == 0:
                    print(f"[ERR] {name} nodes not found — is the framework loaded?", file=sys.stderr)
                    return 1
                print(f"  {name}: {cnt} nodes found")

            print(f"\n{'DRY RUN — ' if args.dry_run else ''}Writing {len(_CROSSWALK)} structured crosswalk edges...\n")

            for src_id, dst_id, note in _CROSSWALK:
                if args.dry_run:
                    print(f"  {src_id} → {dst_id}")
                    print(f"    {note}")
                    skipped += 1
                    continue
                try:
                    session.run(_MERGE_CYPHER, src_id=src_id, dst_id=dst_id, note=note, now=now)
                    created += 1
                except Exception as exc:
                    print(f"  [ERR] {src_id} → {dst_id}: {exc}", file=sys.stderr)
                    errors += 1

    finally:
        driver.close()

    if args.dry_run:
        print(f"\nDry run complete — {skipped} edges would be created.")
    else:
        print(f"\nDone. Created: {created}, Errors: {errors}")

    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
