#!/usr/bin/env python3
"""Orchestrate ingestion of all configured threat reports.

Calls extract_cti_threats.py for each report in the REPORTS list.
Continues on failure and prints per-report status.

Usage:
    python scripts/ingest_all_threat_reports.py [--dry-run]
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent / "extract_cti_threats.py"

_DEFAULT_THREAT_REPORTS_DIR = (
    "/mnt/c/Users/olive/OneDrive/Dokumente/CyberSec/Standards Frameworks/Threat Reports"
)
THREAT_REPORTS_DIR = Path(
    os.environ.get("THREAT_REPORTS_DIR", _DEFAULT_THREAT_REPORTS_DIR)
)

REPORTS = [
    {
        "pdf_filename": "2025-dbir-data-breach-investigations-report.pdf",
        "report_id": "report-verizon-dbir-2025",
        "title": "Verizon Data Breach Investigations Report 2025",
        "publisher": "Verizon",
        "published_at": "2025-05-01",
        "scope": "geographic",
        "page_range": [4, 90],
    },
    {
        "pdf_filename": "Cloudflare Threat Report 2026.pdf",
        "report_id": "report-cloudflare-2026",
        "title": "Cloudflare Threat Report 2026",
        "publisher": "Cloudflare",
        "published_at": "2026-01-01",
        "scope": "vendor",
        "page_range": [3, 80],
    },
    {
        "pdf_filename": "ENISA Threat Landscape 2025.pdf",
        "report_id": "report-enisa-etl-2025",
        "title": "ENISA Threat Landscape 2025",
        "publisher": "ENISA",
        "published_at": "2025-09-01",
        "scope": "geographic",
        "page_range": [4, 150],
    },
    {
        "pdf_filename": "BSI IT-Sicherheitslage TLP-GREEN.pdf",
        "report_id": "report-bsi-lage-2025",
        "title": "BSI IT-Sicherheitslage TLP-GREEN 2025",
        "publisher": "BSI",
        "published_at": "2025-01-01",
        "scope": "geographic",
        "page_range": [0, 100],
    },
    {
        "pdf_filename": "Microsoft Digital Defense Report 2025.pdf",
        "report_id": "report-microsoft-ddr-2025",
        "title": "Microsoft Digital Defense Report 2025",
        "publisher": "Microsoft",
        "published_at": "2025-10-01",
        "scope": "vendor",
        "page_range": [0, 150],
    },
    {
        "pdf_filename": "m-trends-2026-en.pdf",
        "report_id": "report-mandiant-mtrends-2026",
        "title": "Mandiant M-Trends 2026",
        "publisher": "Mandiant",
        "published_at": "2026-04-01",
        "scope": "vendor",
        "page_range": [5, 80],
    },
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Pass --dry-run to each extract_cti_threats.py invocation",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    print(f"Ingesting {len(REPORTS)} threat report(s)...")
    if args.dry_run:
        print("(dry-run mode — no writes)\n")

    results: list[tuple[str, str]] = []

    for report in REPORTS:
        report_id = report["report_id"]
        pdf_path = str(THREAT_REPORTS_DIR / report["pdf_filename"])

        cmd = [
            sys.executable, str(SCRIPT),
            "--pdf", pdf_path,
            "--report-id", report_id,
            "--title", report["title"],
            "--publisher", report["publisher"],
            "--page-range", str(report["page_range"][0]), str(report["page_range"][1]),
        ]

        if report.get("published_at"):
            cmd += ["--published-at", report["published_at"]]
        if report.get("valid_from"):
            cmd += ["--valid-from", report["valid_from"]]
        if report.get("valid_until"):
            cmd += ["--valid-until", report["valid_until"]]
        if report.get("scope"):
            cmd += ["--scope", report["scope"]]
        if report.get("perspective_notes"):
            cmd += ["--perspective-notes", report["perspective_notes"]]
        if args.dry_run:
            cmd.append("--dry-run")

        print(f"\n{'=' * 60}")
        print(f"Report: {report_id}")
        print(f"PDF:    {pdf_path}")
        print(f"{'=' * 60}")

        result = subprocess.run(cmd)

        if result.returncode == 0:
            status = "OK"
        else:
            status = f"FAILED (exit {result.returncode})"

        results.append((report_id, status))

    print(f"\n{'=' * 60}")
    print("Ingestion summary:")
    print(f"{'=' * 60}")
    for report_id, status in results:
        print(f"  {report_id:<40} {status}")

    failed = [r for r, s in results if s != "OK"]
    if failed:
        print(f"\n{len(failed)} report(s) failed.")
        sys.exit(1)
    else:
        print(f"\nAll {len(results)} report(s) completed successfully.")


if __name__ == "__main__":
    main()
