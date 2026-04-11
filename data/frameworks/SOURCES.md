# Framework data sources

This file records provenance for every file under `data/frameworks/`.
See `docs/security/03-operating-guide.md` for the recording procedure.

## Template

For each file, record:

```
## <filename>
- Upstream: <URL>
- SHA-256: <hash>
- Fetched: <YYYY-MM-DD>
- Reviewed: <initials>
- Licence: <licence>
```

---

## Files

## enterprise-attack-17.0.json
- Upstream: https://raw.githubusercontent.com/mitre-attack/attack-stix-data/master/enterprise-attack/enterprise-attack-17.0.json
- SHA-256: c8966a9a55f1723c0082910f4522af448514343f84ffb9a3e757bdd59642d057
- Fetched: 2026-03-20
- Reviewed: OC
- Licence: Apache 2.0 (MITRE ATT&CK)
- Notes: STIX 2.1 bundle, ATT&CK Enterprise v17.0. Hash pin also in attack-stix-pins.json.

## sp800-53-r5-catalog.json
- Upstream: https://raw.githubusercontent.com/usnistgov/oscal-content/main/nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog.json
- SHA-256: 1645df6a370dcb931db2e2d5d70c2f77bc89c38499a416c23a70eb2c0e595bcc
- Fetched: 2026-03-20
- Reviewed: OC
- Licence: Public domain (NIST)
- Notes: OSCAL JSON, NIST SP 800-53 Rev 5 control catalog.

## nist-sp800-53-r5-csf2-crosswalk.json
- Upstream: https://www.nist.gov/system/files/documents/2023/03/17/csf-20-ipd-nist-sp800-53r5-crosswalk.xlsx (converted to JSON)
- SHA-256: 4cc35afeaff6a807af756bc5dab91ec366828bf45250d6ba583ff72bf5a978b1
- Fetched: 2026-03-20
- Reviewed: OC
- Licence: Public domain (NIST)
- Notes: NIST SP 800-53 Rev 5 ↔ CSF 2.0 crosswalk, converted from NIST XLSX.

## ctid-sp800-53-r5-attack-mappings.json
- Upstream: https://github.com/center-for-threat-informed-defense/mappings-explorer/releases
- SHA-256: 7de718ea8dc0da4ff68077668f73325e51c6fcf3e4b0a642e2f3bf3a39a7edba
- Fetched: 2026-03-20
- Reviewed: OC
- Licence: Apache 2.0 (CTID)
- Notes: CTID Mappings Explorer — SP 800-53 Rev 5 to ATT&CK Enterprise mappings.

## ctid-sp800-53-r5-controls.json
- Upstream: https://github.com/center-for-threat-informed-defense/mappings-explorer/releases
- SHA-256: 4f95c19b0b6edef856f5cd25c1b2392607dd4c6dcd7944bc41b70e995cf06d43
- Fetched: 2026-03-20
- Reviewed: OC
- Licence: Apache 2.0 (CTID)
- Notes: CTID control definitions companion file for the SP 800-53 mappings.

## iso-27001-2022.yaml
- Upstream: Manual — structured by OC from ISO/IEC 27001:2022 published text
- SHA-256: 35e63db05f33507d47fd76b5af780abfc1110f59049cec2cf00d8ffd58c5b6dc
- Fetched: 2026-03-20
- Reviewed: OC
- Licence: ISO (restricted; this file contains structural metadata only, not ISO text verbatim)

## nist-csf-2.0.yaml
- Upstream: Manual — structured by OC from NIST CSF 2.0 published text (https://doi.org/10.6028/NIST.CSWP.29)
- SHA-256: 1e58ec700549f4ea78a4c23b648e0821fa31e478e80f726e0f2ab029952067dd
- Fetched: 2026-03-20
- Reviewed: OC
- Licence: Public domain (NIST)

## business-attributes.yaml
- Upstream: Manual — SABSA Business Attribute Profile structured by OC
- SHA-256: c6c76afd20c35789cb17bbd0f68d17fac14389bd8d93fe5426fa962a30df5621
- Fetched: 2026-03-20
- Reviewed: OC
- Licence: Internal (SABSA conceptual framework; this file is original authorship by OC)

## jurisdictions.yaml
- Upstream: Manual — authored by OC
- SHA-256: 3697dff435a3d8b5fc3872a4442b286df70387aaed269e9fec386b9a87e19613
- Fetched: 2026-03-20
- Reviewed: OC
- Licence: Internal
