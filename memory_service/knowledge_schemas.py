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
