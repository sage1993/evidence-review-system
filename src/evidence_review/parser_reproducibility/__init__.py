"""OpenDataLoader warning and reproducibility validation API."""

from evidence_review.parser_reproducibility.contract import (
    OPENDATALOADER_V1_ALLOWED_FIELDS,
    JsonValue,
    ParserRunMetadata,
    ReproducibilityConfig,
    decode_parser_run_metadata,
    decode_reproducibility_config,
)
from evidence_review.parser_reproducibility.queue import (
    ParserReviewQueue,
    ParserReviewQueueEntry,
    build_review_queue,
    decode_review_queue,
)
from evidence_review.parser_reproducibility.report import (
    ParserReproducibilityReport,
    WarningCollectionResult,
    collect_opendataloader_warnings,
    report_bytes,
    validate_opendataloader_reproducibility,
)
from evidence_review.parser_reproducibility.run_manifest import (
    ParserRunManifest,
    build_parser_run_manifest,
    count_source_pdf_pages,
)
from evidence_review.parser_reproducibility.source_identity import (
    SourceIdentity,
    SourceIdentityAuthorityError,
    resolve_source_identity,
)
from evidence_review.parser_reproducibility.warnings import (
    ParserWarning,
    ParserWarningReport,
)

__all__ = [
    "OPENDATALOADER_V1_ALLOWED_FIELDS",
    "JsonValue",
    "ParserReviewQueue",
    "ParserReviewQueueEntry",
    "ParserReproducibilityReport",
    "ParserRunManifest",
    "ParserRunMetadata",
    "ParserWarning",
    "ParserWarningReport",
    "ReproducibilityConfig",
    "SourceIdentity",
    "SourceIdentityAuthorityError",
    "WarningCollectionResult",
    "build_parser_run_manifest",
    "build_review_queue",
    "collect_opendataloader_warnings",
    "count_source_pdf_pages",
    "decode_parser_run_metadata",
    "decode_reproducibility_config",
    "decode_review_queue",
    "report_bytes",
    "resolve_source_identity",
    "validate_opendataloader_reproducibility",
]
