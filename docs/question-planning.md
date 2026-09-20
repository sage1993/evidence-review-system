# AI Question Planning

## Purpose

Evidence Review System uses a bounded external AI planning step before deterministic evidence retrieval when a natural-language question needs semantic decomposition.

The planner is **not an answer engine**. Its role is to preserve the user's question, identify evidence-bearing issues, and propose a bounded set of search requests. The ERS Python core remains responsible for validation, retrieval, rule/math execution, evidence binding, Track A/Track B validation, finalization, and human review.

```text
raw user question
  -> external AI Question Planner
  -> QuestionPlan v2 validator
  -> bounded retrieval adapter
  -> deterministic evidence retrieval
  -> review request
  -> Track A evidence explanation
  -> Track B independent audit
  -> final review packet
  -> human decision
```

## Trust boundary

Planner output is untrusted input. The deterministic core rejects a QuestionPlan that:

- changes the normalized original question;
- supplies a `raw_user_question` that does not normalize to the expected user question;
- contains unknown conclusion/decision/confidence/status fields;
- contains no issues or no search requests;
- exceeds the issue/search/legal-anchor limits;
- contains duplicate IDs or duplicate normalized search requests;
- contains invalid issue dependencies, cycles, or unknown issue references;
- drops user numeric literals or changes their unit semantics;
- claims a `source=user` legal anchor that is not literally supported by the user's question;
- assigns a search-request evidence role that the referenced issue does not require.

Planner-inferred legal anchors use `source=planner`. They are search hypotheses only and do not become authority until matching evidence is retrieved from the finalized evidence store.

## QuestionPlan v3

Current external Question Planner output uses v3. Each issue declares a nonempty
`required_facet_ids` list of atomic answer obligations. Track A must explicitly
bind a fulfilled facet ID to a cited claim, and Track B derives completeness only
from accepted cited claims that cover every required facet. Retrieval
`facet_coverage` remains a retrieval diagnostic and cannot establish answer
completeness. v1/v2 plans remain legacy compatibility inputs; their immutable
RUN artifacts retain their original hash verification semantics.

The current contract is:

```text
format  = evidence-review/question-plan
version = 2
```

A representative v2 document is:

```json
{
  "format": "evidence-review/question-plan",
  "version": 2,
  "original_question": "안심주택 운영기준에서 조건 알려줘",
  "raw_user_question": "안심주택 운영기준에서  조건 알려줘",
  "normalized_question": "안심주택 운영기준에서 조건 알려줘",
  "document_context": [
    {"text": "서울특별시 안심주택 운영기준", "source": "document"}
  ],
  "planner_inference": [
    {"text": "용도지역 변경 기준을 확인한다", "source": "planner"}
  ],
  "facts": [
    {"id": "F1", "text": "사용자가 명시한 사실", "polarity": "positive"}
  ],
  "assumptions": [],
  "issues": [
    {
      "id": "I1",
      "question": "어떤 기준이 적용되는가?",
      "depends_on": [],
      "required_evidence_roles": ["rule"]
    }
  ],
  "legal_anchors": [],
  "search_requests": [
    {
      "id": "S1",
      "issue_ids": ["I1"],
      "text": "적용 기준",
      "kind": "phrase",
      "source": "planner",
      "role": "rule"
    }
  ]
}
```

Current hard limits:

- issues: 8
- search requests: 24
- legal anchors: 20

Evidence roles are `supporting_fact` and `rule`. Each v2 issue declares the roles it requires, and every search request declares which required role it is intended to retrieve.

There is no runtime SIMPLE/COMPOUND/COMPLEX classifier. A simple question should naturally produce a small plan; a complex question may produce multiple issues and dependency edges.

## Raw question and provenance authority

ERS keeps separate fields because they have different authority:

- `raw_user_question` — NFC-normalized user wording with original whitespace/newlines preserved;
- `normalized_question` / `original_question` — canonical collapsed-whitespace form used for validation and deterministic matching;
- `document_context` — context derived from a document, explicitly labeled `source=document`;
- `planner_inference` — planner-generated interpretation, explicitly labeled `source=planner`.

Distinct raw questions must not silently reuse one another's planner handoff. The planning-directory identity includes the full planner bundle, including `raw_user_question`, so two raw inputs that normalize to the same sentence still receive distinct handoff identities.

Document-derived context and planner inference must never be represented as if the user stated them.

## Legacy QuestionPlan v1 compatibility

QuestionPlan v1 is accepted only through the deterministic legacy adapter. It is not the current authoring contract.

For a v1 input, the adapter supplies the current defaults required to decode it into the v2 runtime model. New planner outputs and new documentation examples must use version 2.

## External planner handoff

The deterministic core does not call a model API.

Prepare the external handoff:

```powershell
python -m evidence_review review-question prepare-plan `
  --workspace <workspace> `
  --question "<question>"
```

ERS writes a deterministic planning directory containing:

```text
question-planner-bundle.json
QUESTION_PLANNER_INSTRUCTIONS.md
question-plan-output.json   # expected external output path
```

`question-planner-bundle.json` contains the raw user question, normalized question, and contract identity. Evidence is not exposed to the planner at this stage, and the planner instructions prohibit answering the question.

After an external AI produces `question-plan-output.json`, validate it before retrieval:

```powershell
python -m evidence_review review-question prepare `
  --workspace <workspace> `
  --question "<question>" `
  --question-plan-output <question-plan-output.json>
```

Optional explicit user expansions remain supported:

```powershell
  --expansion "<user supplied search term>"
```

If a user expansion normalizes to the same text as a planner request, the effective query origin remains `user`, while planner search-request and issue lineage is retained.

## Retrieval lineage

A validated planner request is converted to bounded retrieval with immutable issue/search lineage:

```text
QuestionPlan.issue
  -> QuestionPlan.search_request
  -> normalized QueryTerm
  -> retrieval channel
  -> evidence hit
```

Evidence hits may expose matches such as:

```json
{
  "search_request_id": "S2",
  "issue_ids": ["I1"],
  "query_text": "에어컨 실외기 설치",
  "origin": "llm",
  "role": "rule"
}
```

When one evidence item is found through multiple requests or channels, lineage is unioned deterministically. Lineage does **not** add score and does not change channel weights or fusion ranking.

The review request binds the validated plan hash, canonical plan context, question provenance when present, and evidence-level retrieval lineage. This context explains why evidence was retrieved; it does not create citation authority.

## Review-run identity and replay boundary

The canonical validated QuestionPlan is hashed with SHA-256 and bound into the review request.

The deterministic reproducibility boundary starts **after** AI planning:

```text
same validated QuestionPlan
+ same evidence snapshot
+ same deterministic rule/math inputs
=> same deterministic retrieval/review preparation result
```

ERS does not claim that asking an external AI to plan the same question twice necessarily produces the same QuestionPlan. Reproducibility is obtained by preserving and hashing the exact validated plan used for the run.

## Failure states

Planner failure and evidence insufficiency are separate conditions.

| State | Meaning |
|---|---|
| `WAITING_QUESTION_PLAN` | Planner handoff has been prepared and external output is required. |
| `PLANNER_FAILED` | Planner output is missing, unreadable, invalid JSON, or violates the QuestionPlan contract. Retrieval has not started. |
| `RETRIEVAL_NO_EVIDENCE` | A valid QuestionPlan was executed, but deterministic retrieval returned no authoritative evidence. |
| `WAITING_TRACK_A` | A valid plan produced a prepared review run and Track A input is ready. |
| `ABSTAIN` | Final review logic determined that the available validated evidence is insufficient for a supported result. |

`PLANNER_FAILED` must never be reported as `ABSTAIN` or `RETRIEVAL_NO_EVIDENCE`.

## Regression scope for Issue #112

Issue #112 originated from:

```text
에어컨 등 가전제품 설치기준 알려줘
```

The regression corpus intentionally does not contain that complete sentence. The validated fixture plan instead produces bounded searches such as:

```text
가전제품 설치기준
에어컨 설치기준
에어컨 실외기 설치
```

The regression matrix validates raw/normalized question preservation, number/negation preservation, issue dependencies, bounded search generation, evidence-role binding, retrieval lineage, and Track A plan binding. It does not encode or test a real legal conclusion.
