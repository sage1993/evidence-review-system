"""Read-only identifiers for legacy Ansim artifacts.

New writers must not emit these values. Decoders may import them only to read
existing fixtures and workspaces during the compatibility window.
"""

LEGACY_NEXT_ACTION_FORMAT = "ansim/next-action"
LEGACY_REVIEW_PACKET_FORMAT = "ansim/review-packet"
LEGACY_WORKFLOW_STATE_FORMAT = "ansim/workflow-state"
LEGACY_CASE_MANIFEST_FORMAT = "ansim/case-manifest"
LEGACY_HUMAN_ACCEPTANCE_FORMAT = "ansim/human-acceptance"
LEGACY_PAGE_IMAGE_FORMAT = "ansim/page-image"
LEGACY_REVIEW_RUN_REQUEST_FORMAT = "ansim/review-run-request"
LEGACY_EVIDENCE_DB_NAME = "ansim-evidence.sqlite"
LEGACY_RELEASE_ID = "ansim-v1.0"
LEGACY_VISUAL_MANIFEST_CSV = "04_visuals/manifests/visual_manifest.csv"
LEGACY_VISUAL_STATUS = "LEGACY_NON_CANONICAL"
