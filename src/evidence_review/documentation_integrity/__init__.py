"""Offline deterministic documentation-integrity validation."""

from evidence_review.documentation_integrity.classification import (
    DocumentClassificationError,
    classify_document,
)
from evidence_review.documentation_integrity.contract import (
    DocumentationFinding,
    DocumentationIntegrityConfig,
    DocumentationIntegrityReport,
    DocumentClassification,
    FindingSeverity,
    GeneratedDocumentConfig,
    decode_config_bytes,
    finding_sort_key,
    report_bytes,
    report_document,
)
from evidence_review.documentation_integrity.discovery import (
    DiscoveredDocument,
    DocumentDiscoveryError,
    discover_repository_documents,
)

__all__ = [
    "DiscoveredDocument",
    "DocumentClassification",
    "DocumentClassificationError",
    "DocumentDiscoveryError",
    "DocumentationFinding",
    "DocumentationIntegrityConfig",
    "DocumentationIntegrityReport",
    "FindingSeverity",
    "GeneratedDocumentConfig",
    "classify_document",
    "decode_config_bytes",
    "discover_repository_documents",
    "finding_sort_key",
    "report_bytes",
    "report_document",
]
