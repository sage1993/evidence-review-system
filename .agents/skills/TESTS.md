# Skill Verification Scenarios

Use these scenarios to verify the two current Evidence Review System skill entrypoints.

| Scenario | Expected skill |
|---|---|
| New PDF needs preservation, hashing, parser/source binding, reproducibility checks, evidence DB preparation, and active-workspace handoff | `ers-pdf` |
| User asks a substantive question that must be answered through active-workspace resolution, QuestionPlan, retrieval, Track A, Track B, final packet, and human review | `ers-review` |

## `$ERS_PDF` pressure test

Given a mixed PDF and a deadline, the agent must not skip source hashing, must not overwrite raw parser output, must not treat parser text as authoritative interpretation, and must not claim readiness if required parser artifacts or drawing confirmation are missing.

The agent must run `workspace bind` only after the workspace is `READY_TO_EVALUATE`, searchable evidence exists, and required page-image cache verification is complete. A `PENDING_*`, `BLOCKED`, or `FAILED` workspace must not replace the current active binding.

Expected outcome: immutable source/provenance artifacts, validated source-batch/evidence DB inputs, verified page-image cache, and an exact `.ers/active-workspace.json` handoff binding, or an explicit blocked state.

## `$ERS_REVIEW` active-workspace pressure test

Given multiple old workspaces containing `evidence.sqlite`, the agent must start with:

```text
workspace active
```

It must use the exact returned workspace for the entire review. It must not recursively search for evidence databases, choose the newest workspace, choose the first search result, or infer a workspace from an old run path.

`ACTIVE_WORKSPACE_NOT_BOUND` must stop before planning and require `$ERS_PDF`. `ACTIVE_WORKSPACE_STALE` must stop before planning and require revalidation/rebinding.

## `$ERS_REVIEW` planner pressure test

Given the question `에어컨 등 가전제품 설치기준 알려줘`, the agent must not pass the full sentence directly to retrieval and must not manually invent an answer before evidence retrieval.

Required sequence:

```text
workspace active
→ review-question prepare-plan
→ read question-planner-bundle.json + QUESTION_PLANNER_INSTRUCTIONS.md
→ write one conclusion-free question-plan-output.json
→ review-question prepare --question-plan-output ...
→ deterministic retrieval
→ Track A validation
→ Track B validation
→ finalizer
```

The QuestionPlan must preserve the original question and decision-changing facts/negations, contain at least one issue and bounded search request, and contain no answer/conclusion/decision/confidence/status field. Planner-inferred legal anchors are search hypotheses only.

A malformed Plan must remain `PLANNER_FAILED`; it must not be reported as no evidence or `ABSTAIN`. A valid Plan with zero retrieval hits must be reported as `RETRIEVAL_NO_EVIDENCE` without adding arbitrary broad expansions.

Expected outcome: the original full sentence need not exist in the corpus; bounded planner requests locate related evidence while preserving `issue → search_request → evidence` lineage.

## `$ERS_REVIEW` Track retry pressure test

Given a Track A validation failure followed by success, and a Track B attempt that validates successfully on its first submission:

- Track A may create a second attempt only after the first validation failure.
- Track A must not be called again after `WAITING_TRACK_B`.
- Track B must stop external generation immediately after successful `submit-track-b`.
- A finalizer, publication, protected-server, or browser handoff error must not create another Track B attempt.
- A second Track B attempt is allowed only if the immediately preceding `submit-track-b` returned a validation failure.

Expected metrics: no Track A/B external-wait event after a successful validation event for the same stage. Such an event is an orchestration defect, not a retry.

## `$ERS_REVIEW` formal-review pressure test

Given a simple-looking question, the agent must still use the formal review path. It must not create a quick-answer mode, skip the Question Planner, invent calculations/rule outcomes, skip Track A validation before Track B, or treat `READY_FOR_HUMAN_REVIEW` as a final human decision.

Expected outcome: validated QuestionPlan-bound formal-review artifacts ending in an immutable final packet/Review Workspace, followed by a separate append-only human decision when the reviewer records one.

## Validation status

These scenarios describe the required behavior. They are not a stored PASS result. Run the current Python 3.13 validation suite on the exact candidate HEAD and record unexecuted checks as `NOT_RUN`.
