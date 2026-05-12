"""
memory_service/knowledge_schemas.py — Validated enum sets for the information security knowledge layer.

Shared by knowledge_routes.py (request validation) and ETL scripts (ingest validation).
All values are normalised to lowercase on write.
"""

SABSA_LAYERS: frozenset[str] = frozenset({
    "contextual",
    "conceptual",
    "logical",
    "physical",
    "component",
    "operational",
})

CONTROL_DOMAINS: frozenset[str] = frozenset({
    "access-control",
    "asset-management",
    "business-continuity",
    "compliance",
    "cryptography",
    "data-protection",
    "governance",
    "human-resources",
    "identity-management",
    "incident-management",
    "network-security",
    "operations-security",
    "physical-security",
    "risk-management",
    "secure-development",
    "supplier-relationships",
    "threat-intelligence",
    "vulnerability-management",
})

JURISDICTION_TYPES: frozenset[str] = frozenset({
    "geographic",
    "sectoral",
})

ORGANISATION_TYPES: frozenset[str] = frozenset({
    "employer",
    "client",
    "regulatory-body",
    "standards-body",
})

CONTROL_RELATIONSHIP_TYPES: frozenset[str] = frozenset({
    "context",
    "evidence",
    "gap",
})

DOCUMENT_POLICY_LEVELS: frozenset[str] = frozenset({
    "strategic",
    "tactical",
    "operational",
    "procedure",
})

STATEMENT_TYPES: frozenset[str] = frozenset({
    "normative",      # creates obligations ("shall", "must")
    "informative",    # guidance, notes, examples
    "definitional",   # terms and definitions
    "reference",      # cross-references to other standards
    "structural",     # section headings without substantive text
})

NORMATIVE_MODALITIES: frozenset[str] = frozenset({
    "must",
    "shall",
    "should",
    "may",
    "must_not",
    "shall_not",
    "should_not",
})

CHUNK_STATUSES: frozenset[str] = frozenset({
    "unmatched",    # ingested, not yet linked to any tree node
    "matched",      # candidate match found, pending confirmation
    "confirmed",    # human or automated confirmation of SUPPORTS edge
    "superseded",   # content replaced by a newer chunk
})

THREAT_REPORT_SCOPES: frozenset[str] = frozenset({
    "geographic", "sectoral", "vendor",
})

IDENTIFIES_SEVERITIES: frozenset[str] = frozenset({
    "critical", "high", "medium", "low",
})

IDENTIFIES_CONFIDENCES: frozenset[str] = frozenset({
    "high", "medium", "low",
})

IDENTIFIES_TRENDS: frozenset[str] = frozenset({
    "increasing", "stable", "decreasing",
})

ASSET_TYPES: frozenset[str] = frozenset({
    "IT", "OT", "IoT", "IT-OT-integration",
})

ASSET_EXPOSURES: frozenset[str] = frozenset({
    "internet-facing", "internal", "air-gapped",
})

ASSET_DATA_CLASSIFICATIONS: frozenset[str] = frozenset({
    "public", "internal", "confidential", "restricted",
})

# ---------------------------------------------------------------------------
# WP-113 — T100-aligned SABSA / BusinessAttribute constants
# ---------------------------------------------------------------------------

BA_STATUSES: frozenset[str] = frozenset({"active", "deprecated"})

SABSA_PERSPECTIVES: frozenset[str] = frozenset({
    "assets", "motivation", "process", "people", "location", "time",
})

SABSA_MATRICES: frozenset[str] = frozenset({"main", "service-management"})

MATRIX_LAYERS_MAIN: frozenset[str] = frozenset({
    "contextual", "conceptual", "logical", "physical", "component", "operational",
})

# Service Management Matrix layers — read from R101 Table 3 (p.8, TSI-R101-SABSA-Matrices-2018-Release-Notes.pdf).
# The 5 expansion rows beneath the Management Architecture repeat-row use the same 5 layer names
# as the main matrix (all except "operational", which is the top-level SM row itself).
MATRIX_LAYERS_SERVICE_MGMT: frozenset[str] = frozenset({
    "contextual", "conceptual", "logical", "physical", "component",
})

BA_GROUPS: frozenset[str] = frozenset({
    "management",
    "user",
    "operational",
    "risk-management",
    "technical-strategy",
    "business-strategy",
    "legal-regulatory",
})

BA_TIERS: frozenset[str] = frozenset({"primitive-root", "ict-group", "ict-leaf"})

# T100 §3.4.2 stereotype catalogue — initial set for WP-113 (v2.5, Feb 2026).
# Extended as additional T100-stereotyped node types are introduced in follow-on WPs.
T100_STEREOTYPES: frozenset[str] = frozenset({"sabsa-attribute"})

INFLUENCE_POLARITIES: frozenset[str] = frozenset({"positive", "negative"})

INFLUENCE_STATUSES: frozenset[str] = frozenset({
    "draft-curated",
    "curated",
    "auto-inferred-embedding",
    "auto-inferred-traversal",
})

CELL_ROLES: frozenset[str] = frozenset({"main-matrix-cell", "service-mgmt-cell"})

POLICY_STATUS: frozenset[str] = frozenset({
    "draft", "active", "deprecated", "retired",
})

PARAM_TYPE: frozenset[str] = frozenset({
    "string", "integer", "enum", "select", "datetime", "duration",
})

ASSET_CLASS_KIND: frozenset[str] = frozenset({
    "it", "ot", "iot", "integration", "data", "process", "people", "facility",
})
