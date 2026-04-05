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
