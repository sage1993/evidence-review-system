# Skill Verification Scenarios

Use these scenarios to verify the Evidence Review System skill entrypoints and the REFERENCE_DOCUMENT / case-visual boundary.

| Scenario | Expected path |
|---|---|
| `이 법규 PDF를 ERS 근거자료로 등록해` | `ers-pdf` → `REFERENCE_DOCUMENT` |
| New reference PDF needs preservation, hashing, parser/source binding, reproducibility checks, and evidence DB preparation | `ers-pdf` |
| User asks a substantive question that must be answered through QuestionPlan, retrieval, Track A, Track B, final packet, and human review | `ers-review` |
| `이 PDF 도면을 보고 출입구 위치가 적절한지 검토해` | `ers-review` → `CASE_DRAWING`; do **not** invoke `ers-pdf` for the case drawing |
| `이 PDF 도면에서 문제가 있는 부분을 찾아줘` | `ers-review` → `CASE_DRAWING` visual analysis |
| `이 PNG 평면을 보고 검토해` | `ers-review` → `SUPPORTING_IMAGE` or `CASE_DRAWING` visual analysis |
| `이 PDF를 근거자료로 등록한 뒤 질문에 답해` | first `ers-pdf` as `REFERENCE_DOCUMENT`, then `ers-review` |

## `$ERS_PDF` pressure test

Given a REFERENCE_DOCUMENT PDF and a deadline, the agent must not skip source hashing, must not overwrite raw parser output, must not treat parser text as authoritative interpretation, and must not claim readiness if required parser artifacts are missing.

Expected outcome: immutable source/provenance artifacts, validated source-batch/evidence DB inputs, verified normative page-image cache, or an explicit blocked state.

A PDF extension alone is never sufficient to activate this skill. If the user asks to inspect the PDF drawing itself, `$ERS_PDF` is the wrong route.

## CASE drawing routing pressure test

Given `이 PDF 도면을 보고 판단해`, the agent must preserve the file as `CASE_DRAWING` and route it through drawing intake and visual analysis. It must not run OpenDataLoader reference ingestion, must not require parser reproducibility, and must not convert a case visual failure into `PARSER_SOURCE_PDF_INVALID`.

Given `49.91㎡ A형, 2Bay, 2R+1B인지 첨부 이미지를 보고 확인해`, the question prose may be preserved as a user assertion, but those values must not become visual evidence until the actual image/page is inspected and a source/page/geometry-bound visual output passes runtime validation.

Expected outcome: case visual source hash is bound to the formal review request, visual analysis is required before any drawing candidate is created, and the final workspace can show the actual source with validated geometry overlay.

## `$ERS_REVIEW` planner pressure test

Given the question `에어컨 등 가전제품 설치기준 알려줘`, the agent must not pass the full sentence directly to retrieval and must not manually invent an answer before evidence retrieval.

Required sequence without case visual attachments:

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

Required sequence with case visual attachments:

```text
review-question prepare-plan
→ validated QuestionPlan
→ review-question prepare --case-drawing/--supporting-image ...
→ immutable drawing intake
→ visual-analysis handoff and validation
→ deterministic retrieval
→ Track A validation with separated normative/visual lineage
→ Track B validation
→ finalizer
```

The QuestionPlan must preserve the original question and decision-changing facts/negations, contain at least one issue and bounded search request, and contain no answer/conclusion/decision/confidence/status field. Planner-inferred legal anchors are search hypotheses only.

A malformed Plan must remain `PLANNER_FAILED`; it must not be reported as no evidence or `ABSTAIN`. A valid Plan with zero retrieval hits must be reported as `RETRIEVAL_NO_EVIDENCE` without adding arbitrary broad expansions.

## `$ERS_REVIEW` formal-review pressure test

Given a simple-looking question, the agent must still use the formal review path. It must not create a quick-answer mode, skip the Question Planner, invent calculations/rule outcomes, skip Track A validation before Track B, or treat `READY_FOR_HUMAN_REVIEW` as a final human decision.

Visual observations are case facts, not legal authority. A drawing candidate cannot replace a required normative citation, and an unconfirmed candidate cannot be promoted to a deterministic Math/Rule input.

Expected outcome: validated QuestionPlan-bound formal-review artifacts ending in an immutable final packet/Review Workspace, followed by a separate append-only human decision when the reviewer records one.

## Validation status

These scenarios describe the required behavior. They are not a stored PASS result. Run the current Python 3.13 validation suite on the exact candidate HEAD and record unexecuted checks as `NOT_RUN`.
