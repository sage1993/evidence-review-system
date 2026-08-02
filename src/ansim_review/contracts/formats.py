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
