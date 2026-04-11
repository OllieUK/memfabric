#!/usr/bin/env python3
"""Extract CTI threats from a PDF threat report and ingest into the knowledge graph.

Usage:
    python scripts/extract_cti_threats.py \\
        --pdf PATH \\
        --report-id REPORT_ID \\
        --title TITLE \\
        --publisher PUBLISHER \\
        [--published-at DATE] \\
        [--valid-from DATE] \\
        [--valid-until DATE] \\
        [--scope SCOPE] \\
        [--perspective-notes NOTES] \\
        [--dry-run] \\
        [--dedup-threshold 0.15] \\
        [--page-range START END]

Reads config from .env (API_BASE_URL).
"""
import argparse
import hashlib
import re
import sys
from pathlib import Path

import httpx
import pdfplumber
from pydantic_settings import BaseSettings, SettingsConfigDict

try:
    from pdf_utils import words_to_lines, line_text
except ImportError:
    from scripts.pdf_utils import words_to_lines, line_text

# Ensure project root on path so memory_service is importable
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
from memory_service.ingest_guard import guard_chunk


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

class CTISettings(BaseSettings):
    api_base_url: str = "http://localhost:8000"
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


# ---------------------------------------------------------------------------
# CTI extraction vocabulary
# ---------------------------------------------------------------------------

BEHAVIOR_INDICATORS = [
    "used", "executed", "deployed", "leveraged", "exploited",
    "established", "created", "modified", "downloaded", "uploaded",
    "exfiltrated", "injected", "enumerated", "spawned", "dropped",
    "persisted", "escalated", "moved laterally", "collected",
    "encrypted", "compressed", "encoded", "obfuscated",
    "observed", "detected", "identified", "reported", "targeted",
    "affected", "compromised", "attacked", "breached",
]

TECHNIQUE_KEYWORDS: dict[str, str] = {
    # Initial Access
    "phishing attachment": "T1566.001",
    "phishing link": "T1566.002",
    "spearphishing": "T1566",
    "phishing": "T1566",
    "supply chain": "T1195",
    "exploit public": "T1190",
    "valid account": "T1078",
    # Execution
    "powershell": "T1059.001",
    "command line": "T1059.003",
    "wmi": "T1047",
    "scheduled task": "T1053.005",
    # Persistence
    "registry run": "T1547.001",
    "web shell": "T1505.003",
    # Credential Access
    "credential stuffing": "T1110.004",
    "password spray": "T1110.003",
    "kerberoasting": "T1558.003",
    "pass the hash": "T1550.002",
    "credential dumping": "T1003",
    "lsass": "T1003.001",
    "brute force": "T1110",
    "credential": "T1110",
    # Lateral Movement
    "lateral movement": "T1021",
    "remote desktop": "T1021.001",
    "rdp": "T1021.001",
    "smb": "T1021.002",
    # Collection/Exfiltration
    "data exfiltration": "T1041",
    "exfiltration": "T1041",
    "dns tunneling": "T1071.004",
    "data staging": "T1074",
    # Impact
    "ransomware": "T1486",
    "wiper": "T1485",
    "data destruction": "T1485",
    "denial of service": "T1498",
    "ddos": "T1498",
    "encryption": "T1486",
    # Resource Development
    "infrastructure": "T1583",
    # Cloud
    "cloud misconfiguration": "T1530",
    "cloud storage": "T1530",
    # Resource Hijacking
    "cryptojacking": "T1496",
    "resource hijacking": "T1496",
    # Business Email Compromise
    "business email compromise": "T1534",
    "bec": "T1534",
}

SEVERITY_SIGNALS: dict[str, str] = {
    "critical": "critical",
    "severe": "critical",
    "major": "critical",
    "widespread": "high",
    "significant": "high",
    "moderate": "medium",
}

TREND_SIGNALS: dict[str, str] = {
    "increasing": "increasing",
    "growing": "increasing",
    "rise": "increasing",
    "risen": "increasing",
    "more": "increasing",
    "declining": "decreasing",
    "decreasing": "decreasing",
    "fewer": "decreasing",
    "falling": "decreasing",
}


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

def extract_severity(text: str) -> str:
    t = text.lower()
    for word, sev in SEVERITY_SIGNALS.items():
        if word in t:
            return sev
    return "high"


def extract_trend(text: str) -> str:
    t = text.lower()
    for word, trend in TREND_SIGNALS.items():
        if word in t:
            return trend
    return "stable"


def match_techniques(text: str) -> list[tuple[str, str]]:
    """Return list of (keyword, technique_id) matches."""
    t = text.lower()
    matches = []
    for keyword, tech_id in TECHNIQUE_KEYWORDS.items():
        if keyword in t:
            matches.append((keyword, tech_id))
    return matches


SOURCE_TERMINOLOGY_MAX = 200


def extract_sentences_from_pdf(pdf_path: str, page_range: list[int]) -> list[str]:
    """Extract prose sentences from PDF using word-level bounding box extraction."""
    lines = []
    try:
        pdf = pdfplumber.open(pdf_path)
    except Exception as exc:
        print(f"[ERROR] Cannot open PDF '{pdf_path}': {exc}", file=sys.stderr)
        sys.exit(1)
    with pdf:
        pages = pdf.pages[page_range[0]:page_range[1]]
        for page in pages:
            words = page.extract_words(x_tolerance=2, y_tolerance=3)
            if not words:
                continue
            for line_words in words_to_lines(words):
                text = line_text(line_words).strip()
                if text:
                    lines.append(text)
    full_text = " ".join(lines)
    sentences = re.split(r"(?<=[.!?])\s+", full_text)
    return [s.strip() for s in sentences if len(s.strip()) > 20]


def find_duplicate_threat(client: httpx.Client, text: str, threshold: float) -> str | None:
    """Return existing threat id if a near-duplicate exists, else None."""
    try:
        r = client.post("/knowledge/search/threats", json={"query": text, "limit": 1})
    except httpx.HTTPError as exc:
        print(f"  [WARN] search/threats request failed: {exc} — skipping dedup check", file=sys.stderr)
        return None
    if r.status_code != 200:
        print(f"  [WARN] search/threats returned {r.status_code} — skipping dedup check", file=sys.stderr)
        return None
    hits = r.json()
    if hits and hits[0]["distance"] < threshold:
        return hits[0]["id"]
    return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--pdf", required=True, help="Path to the threat report PDF")
    parser.add_argument("--report-id", required=True, help="Unique report ID")
    parser.add_argument("--title", required=True, help="Report title")
    parser.add_argument("--publisher", required=True, help="Report publisher")
    parser.add_argument("--published-at", default=None, help="Publication date (YYYY-MM-DD)")
    parser.add_argument("--valid-from", default=None, help="Validity start date (YYYY-MM-DD)")
    parser.add_argument("--valid-until", default=None, help="Validity end date (YYYY-MM-DD)")
    parser.add_argument("--scope", default=None, help="Report scope (e.g. geographic, vendor)")
    parser.add_argument("--perspective-notes", default=None, help="Free-text perspective notes")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be ingested but make no API calls")
    parser.add_argument("--dedup-threshold", type=float, default=0.15, help="Distance threshold for deduplication (default: 0.15)")
    parser.add_argument("--page-range", nargs=2, type=int, default=[0, 100], metavar=("START", "END"), help="Page range to extract (0-indexed, exclusive end)")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    cfg = CTISettings()

    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"Error: PDF not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    try:
        with httpx.Client(base_url=cfg.api_base_url, timeout=60) as client:
            # 1. Create ThreatReport node
            report_payload = {
                "id": args.report_id,
                "title": args.title,
                "publisher": args.publisher,
            }
            if args.published_at:
                report_payload["published_at"] = args.published_at
            if args.valid_from:
                report_payload["valid_from"] = args.valid_from
            if args.valid_until:
                report_payload["valid_until"] = args.valid_until
            if args.scope:
                report_payload["scope"] = args.scope
            if args.perspective_notes:
                report_payload["perspective_notes"] = args.perspective_notes

            if not args.dry_run:
                r = client.post("/knowledge/threat-reports", json=report_payload)
                r.raise_for_status()
            print(f"[+] ThreatReport: {args.report_id}")

            # 2. Extract sentences from PDF
            sentences = extract_sentences_from_pdf(str(pdf_path), args.page_range)
            print(f"[+] Extracted {len(sentences)} sentences from PDF (pages {args.page_range[0]}–{args.page_range[1]})")

            # 3. Filter to behaviour-relevant sentences with technique matches
            candidates: list[tuple[str, list[tuple[str, str]]]] = []
            for sentence in sentences:
                lower = sentence.lower()
                has_verb = any(verb in lower for verb in BEHAVIOR_INDICATORS)
                techniques = match_techniques(lower)
                if has_verb and techniques:
                    candidates.append((sentence, techniques))

            print(f"[+] {len(candidates)} candidate threat sentences (behaviour verb + technique keyword)")

            # Deduplicate candidates within this report by exact sentence text
            seen_sentences: set[str] = set()
            deduped_candidates = []
            for sentence, techniques in candidates:
                if sentence not in seen_sentences:
                    seen_sentences.add(sentence)
                    deduped_candidates.append((sentence, techniques))
            candidates = deduped_candidates

            # 4. Deduplicate against graph, create Threat nodes, create edges
            new_threats = 0
            deduped = 0
            technique_edges = 0

            for sentence, techniques in candidates:
                if guard_chunk(sentence, source=f"extract_cti_threats:{args.report_id}"):
                    print(f"  [SKIP] threat quarantined by ingest guard", file=sys.stderr)
                    continue

                existing_id = None if args.dry_run else find_duplicate_threat(client, sentence, args.dedup_threshold)

                if existing_id:
                    threat_id = existing_id
                    deduped += 1
                else:
                    threat_id = f"threat-{args.report_id}-{hashlib.sha1(sentence.encode()).hexdigest()[:8]}"
                    if not args.dry_run:
                        r = client.post("/knowledge/threats", json={
                            "id": threat_id,
                            "text": sentence,
                            "tags": [t[1] for t in techniques],
                        })
                        if r.status_code not in (200, 201):
                            print(f"  [WARN] Failed to create threat {threat_id}: {r.text}", file=sys.stderr)
                            continue
                    new_threats += 1

                # IDENTIFIES edge
                if not args.dry_run:
                    r = client.post("/knowledge/identifies", json={
                        "threat_report_id": args.report_id,
                        "threat_id": threat_id,
                        "severity": extract_severity(sentence),
                        "confidence": "high",
                        "trend": extract_trend(sentence),
                        "source_terminology": sentence[:SOURCE_TERMINOLOGY_MAX],
                    })
                    if r.status_code not in (200, 201):
                        print(f"  [WARN] IDENTIFIES edge failed for {threat_id}: {r.status_code}", file=sys.stderr)

                # MAPPED_TO_TECHNIQUE edges
                seen_tech: set[str] = set()
                for keyword, tech_id in techniques:
                    if tech_id in seen_tech:
                        continue
                    seen_tech.add(tech_id)
                    framework_id = f"attack-enterprise.{tech_id}"
                    if not args.dry_run:
                        r = client.post("/knowledge/mapped-to-technique", json={
                            "threat_id": threat_id,
                            "framework_id": framework_id,
                        })
                        if r.status_code in (200, 201):
                            technique_edges += 1
                        elif r.status_code == 404:
                            pass  # ATT&CK node not in graph for this technique_id
                        else:
                            print(f"  [WARN] MAPPED_TO_TECHNIQUE failed for {threat_id}→{framework_id}: {r.status_code}", file=sys.stderr)
                    else:
                        technique_edges += 1

    except httpx.HTTPError as exc:
        print(f"[ERROR] HTTP request failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"\n=== Summary for {args.report_id} ===")
    print(f"  Candidate threats: {len(candidates)}")
    print(f"  New Threat nodes:  {new_threats}")
    print(f"  Deduplicated:      {deduped}")
    print(f"  Technique edges:   {technique_edges}")
    if args.dry_run:
        print("  (dry-run — no writes)")


if __name__ == "__main__":
    main()
