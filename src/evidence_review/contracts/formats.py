"""Canonical user-facing artifact format identifiers."""

from typing import Final, Literal

NEXT_ACTION_FORMAT: Final[Literal["evidence-review/next-action"]] = (
    "evidence-review/next-action"
)
REVIEW_PACKET_FORMAT: Final[Literal["evidence-review/review-packet"]] = (
    "evidence-review/review-packet"
)
WORKFLOW_STATE_FORMAT: Final[Literal["evidence-review/workflow-state"]] = (
    "evidence-review/workflow-state"
)
REVIEW_REQUEST_FORMAT: Final[Literal["evidence-review/review-request"]] = (
    "evidence-review/review-request"
)
WORKFLOW_EVENT_FORMAT: Final[Literal["evidence-review/workflow-event"]] = (
    "evidence-review/workflow-event"
)
REFERENCE_INGESTION_RECEIPT_FORMAT: Final[
    Literal["evidence-review/reference-ingestion-receipt"]
] = "evidence-review/reference-ingestion-receipt"
CASE_MANIFEST_FORMAT: Final[Literal["evidence-review/case-manifest"]] = (
    "evidence-review/case-manifest"
)
CONFIRMED_INPUT_SET_FORMAT: Final[Literal["evidence-review/confirmed-input-set"]] = (
    "evidence-review/confirmed-input-set"
)
DRAWING_QUALITY_FORMAT: Final[Literal["evidence-review/drawing-quality"]] = (
    "evidence-review/drawing-quality"
)
PAGE_IMAGE_FORMAT: Final[Literal["evidence-review/page-image"]] = (
    "evidence-review/page-image"
)
SOURCE_INVENTORY_FORMAT: Final[Literal["evidence-review/source-inventory"]] = (
    "evidence-review/source-inventory"
)
UNRESOLVED_LINKS_FORMAT: Final[Literal["evidence-review/unresolved-links"]] = (
    "evidence-review/unresolved-links"
)
CODEX_WORKSPACE_FORMAT: Final[Literal["evidence-review/codex-workspace"]] = (
    "evidence-review/codex-workspace"
)
WEB_RUNTIME_FORMAT: Final[Literal["evidence-review/chatgpt-web-runtime"]] = (
    "evidence-review/chatgpt-web-runtime"
)
HUMAN_ATTESTATION_FORMAT: Final[Literal["evidence-review/human-attestation"]] = (
    "evidence-review/human-attestation"
)
HUMAN_ATTESTATION_STATUS_FORMAT: Final[
    Literal["evidence-review/human-attestation-status"]
] = "evidence-review/human-attestation-status"
RELEASE_FORMAT: Final[Literal["evidence-review/release"]] = (
    "evidence-review/release"
)
RELEASE_VALIDATION_FORMAT: Final[
    Literal["evidence-review/release-validation"]
] = "evidence-review/release-validation"
RELEASE_OUTPUT_VALIDATION_FORMAT: Final[
    Literal["evidence-review/release-output-validation"]
] = "evidence-review/release-output-validation"
LEGACY_LINEAGE_MANIFEST_FORMAT: Final[
    Literal["evidence-review/legacy-lineage-manifest"]
] = "evidence-review/legacy-lineage-manifest"
LEGACY_LINEAGE_ALIASES_FORMAT: Final[
    Literal["evidence-review/legacy-lineage-aliases"]
] = "evidence-review/legacy-lineage-aliases"
LEGACY_LINEAGE_MIGRATION_REPORT_FORMAT: Final[
    Literal["evidence-review/legacy-lineage-migration-report"]
] = "evidence-review/legacy-lineage-migration-report"
RULE_GOLDEN_REPORT_FORMAT: Final[
    Literal["evidence-review/rule-golden-report"]
] = "evidence-review/rule-golden-report"
RULE_ACTIVATION_APPROVAL_FORMAT: Final[
    Literal["evidence-review/rule-activation-approval"]
] = "evidence-review/rule-activation-approval"
ACTIVE_RULE_MANIFEST_FORMAT: Final[
    Literal["evidence-review/active-rule-manifest"]
] = "evidence-review/active-rule-manifest"
RULE_ACTIVATION_REPORT_FORMAT: Final[
    Literal["evidence-review/rule-activation-report"]
] = "evidence-review/rule-activation-report"
RULE_SELECTION_RESULT_FORMAT: Final[
    Literal["evidence-review/rule-selection-result"]
] = "evidence-review/rule-selection-result"
DOCUMENTATION_INTEGRITY_CONFIG_FORMAT: Final[
    Literal["evidence-review/documentation-integrity-config"]
] = "evidence-review/documentation-integrity-config"
DOCUMENTATION_INTEGRITY_REPORT_FORMAT: Final[
    Literal["evidence-review/documentation-integrity-report"]
] = "evidence-review/documentation-integrity-report"
REVIEW_MATTER_FORMAT: Final[Literal["evidence-review/review-matter"]] = (
    "evidence-review/review-matter"
)
MATTER_EVENT_FORMAT: Final[Literal["evidence-review/matter-event"]] = (
    "evidence-review/matter-event"
)
MATTER_SOURCE_BINDING_FORMAT: Final[
    Literal["evidence-review/matter-source-binding"]
] = "evidence-review/matter-source-binding"
