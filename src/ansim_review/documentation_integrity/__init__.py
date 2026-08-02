"""Offline deterministic documentation-integrity validation."""

from ansim_review.documentation_integrity.contract import (
    DocumentClassification,
    DocumentationFinding,
    DocumentationIntegrityConfig,
    DocumentationIntegrityReport,
    FindingSeverity,
    GeneratedDocumentConfig,
    decode_config_bytes,
    finding_sort_key,
    report_bytes,
    report_document,
)

__all__ = [
    "DocumentClassification",
    "DocumentationFinding",
    "DocumentationIntegrityConfig",
    "DocumentationIntegrityReport",
    "FindingSeverity",
    "GeneratedDocumentConfig",
    "decode_config_bytes",
    "finding_sort_key",
    "report_bytes",
    "report_document",
]
