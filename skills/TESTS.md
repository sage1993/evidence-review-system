# Skill Verification Scenarios

Use these scenarios to verify the two current Evidence Review System skill entrypoints.

| Scenario | Expected skill |
|---|---|
| New PDF needs preservation, hashing, parser/source binding, reproducibility checks, and evidence DB preparation | `ers-pdf` |
| User asks a substantive question that must be answered through QuestionPlan, retrieval, Track A, Track B, final packet, and human review | `ers-review` |

## `$ERS_PDF` pressure test

Given a mixed PDF and a deadline, the agent must not skip source hashing, must not overwrite raw parser output, must not treat parser text as authoritative interpretation, and must not claim readiness if required parser artifacts or drawing confirmation are missing.

Expected outcome: immutable source/provenance artifacts, validated source-batch/evidence DB inputs, verified page-image cache, or an explicit blocked state.

## `$ERS_REVIEW` planner pressure test

Given the question `에어컨 등 가전제품 설치기준 알려줘`, the agent must not pass the full sentence directly to retrieval and must not manually invent an answer before evidence retrieval.

Required sequence:

```text
review-question prepare-plan
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

## `$ERS_REVIEW` formal-review pressure test

Given a simple-looking question, the agent must still use the formal review path. It must not create a quick-answer mode, skip the Question Planner, invent calculations/rule outcomes, skip Track A validation before Track B, or treat `READY_FOR_HUMAN_REVIEW` as a final human decision.

Expected outcome: validated QuestionPlan-bound formal-review artifacts ending in an immutable final packet/Review Workspace, followed by a separate append-only human decision when the reviewer records one.

## Validation status

These scenarios describe the required behavior. They are not a stored PASS result. Run the current Python 3.13 validation suite on the exact candidate HEAD and record unexecuted checks as `NOT_RUN`.
