# Threat intelligence sources

This file records provenance for CTI files under `data/threats/` and for PDF threat reports ingested via `scripts/ingest_all_threat_reports.py`.
See `docs/security/03-operating-guide.md` for the recording procedure (PDF review runbook must be followed before ingesting any report).

## Template

```
## <filename or report name>
- Upstream: <URL or "Manual — <source organisation>">
- SHA-256: <hash of PDF>
- Fetched: <YYYY-MM-DD>
- Reviewed: <initials>
- Notes: <e.g. "Verizon DBIR 2024">
```

---

## Static files

## assets.yaml
- Upstream: Manual — authored by OC
- SHA-256: (small config file; hash not required)
- Fetched: 2026-03-20
- Reviewed: OC
- Licence: Internal

---

## Ingested threat reports

Reports are ingested via `scripts/ingest_all_threat_reports.py` and `scripts/extract_cti_threats.py`.
Each report must be reviewed per the PDF runbook in `docs/security/03-operating-guide.md` before ingestion.

<!-- Add one entry per ingested threat report using the template above.
     Include the PDF SHA-256 (sha256sum <file.pdf>) and the report_id used during ingestion. -->
