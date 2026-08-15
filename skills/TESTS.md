# Skill Verification Scenarios

Use these scenarios to verify the two current Evidence Review System skill entrypoints.

| Scenario | Expected skill |
|---|---|
| New PDF needs preservation, hashing, parser/source binding, reproducibility checks, and evidence DB preparation | `ers-pdf` |
| User asks a substantive question that must be answered through retrieval, Track A, Track B, final packet, and human review | `ers-review` |

## `$ERS_PDF` pressure test

Given a mixed PDF and a deadline, the agent must not skip source hashing, must not overwrite raw parser output, must not treat parser text as authoritative interpretation, and must not claim readiness if required parser artifacts or drawing confirmation are missing.

Expected outcome: immutable source/provenance artifacts, validated source-batch/evidence DB inputs, verified page-image cache, or an explicit blocked state.

## `$ERS_REVIEW` pressure test

Given a simple-looking question, the agent must still use the formal review path. It must not create a quick-answer mode, invent calculations/rule outcomes, skip Track A validation before Track B, or treat `READY_FOR_HUMAN_REVIEW` as a final human decision.

Expected outcome: validated formal-review artifacts ending in an immutable final packet/Review Workspace, followed by a separate append-only human decision when the reviewer records one.

## Validation status

These scenarios describe the required behavior. They are not a stored PASS result. Run the current Python 3.13 validation suite on the exact candidate HEAD and record unexecuted checks as `NOT_RUN`.
