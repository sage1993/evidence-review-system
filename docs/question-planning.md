# AI Question Planning

## Purpose

Evidence Review System uses a bounded external AI planning step before deterministic evidence retrieval when a natural-language question needs semantic decomposition.

The planner is **not an answer engine**. Its only role is to preserve the user's question, identify evidence-bearing issues, and propose a bounded set of search requests. The ERS Python core remains responsible for validation, retrieval, rule/math execution, evidence binding, Track A/Track B validation, finalization, and human review.

```text
user question
  -> external AI Question Planner
  -> QuestionPlan validator
  -> bounded retrieval adapter
  -> deterministic evidence retrieval
  -> review request
  -> Track A evidence explanation
  -> Track B audit
  -> final review packet
  -> human decision
```

## Trust boundary

The planner output is untrusted input.

The deterministic core rejects a QuestionPlan that:

- changes the normalized original question;
- contains unknown fields such as `answer`, `conclusion`, `decision`, `confidence`, or `status`;
- contains no issues or no search requests;
- exceeds the issue/search/legal-anchor limits;
- contains duplicate IDs or duplicate normalized search requests;
- contains invalid issue dependencies, cycles, or unknown issue references;
- claims a `source=user` legal anchor that is not literally present in the user's normalized question.

Planner-inferred legal anchors use `source=planner`. They are search hypotheses only and do not become authority until matching evidence is retrieved from the evidence store.

## QuestionPlan v1

A validated plan has the following shape:

```json
{
  "format": "evidence-review/question-plan",
  "version": 1,
  "original_question": "...",
  "facts": [
    {"id": "F1", "text": "...", "polarity": "positive"}
  ],
  "assumptions": [],
  "issues": [
    {"id": "I1", "question": "...", "depends_on": []}
  ],
  "legal_anchors": [],
  "search_requests": [
    {
      "id": "S1",
      "issue_ids": ["I1"],
      "text": "...",
      "kind": "phrase",
      "source": "planner"
    }
  ]
}
```

Current hard limits:

- issues: 8
- search requests: 24
- legal anchors: 20

There is no runtime SIMPLE/COMPOUND/COMPLEX classifier. A simple question should naturally produce a small plan; a complex question may produce multiple issues and dependency edges.

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

`question-planner-bundle.json` contains the original question and contract identity only. Evidence is not exposed to the planner at this stage, and the planner instructions explicitly prohibit answering the question.

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

If a user expansion normalizes to the same text as a planner request, the effective query origin remains `user`, while the planner search-request and issue lineage is retained.

## Retrieval lineage

A validated planner request is converted to an existing retrieval expansion with `origin=llm` plus immutable lineage identifiers.

```text
QuestionPlan.issue
  -> QuestionPlan.search_request
  -> normalized QueryTerm
  -> retrieval channel
  -> evidence hit
```

Evidence hits may expose `matches` such as:

```json
{
  "search_request_id": "S2",
  "issue_ids": ["I1"],
  "query_text": "에어컨 실외기 설치",
  "origin": "llm"
}
```

When one evidence item is found through multiple requests or channels, lineage is unioned deterministically. Lineage does **not** add score and does not change channel weights or fusion ranking.

The review request also binds retrieval lineage into `inputs.retrieval_lineage` as an evidence-level array:

```json
[
  {
    "evidence_id": "E1",
    "citation_id": "CIT-E1",
    "matches": [
      {
        "search_request_id": "S2",
        "issue_ids": ["I1"],
        "query_text": "에어컨 실외기 설치",
        "origin": "llm"
      }
    ]
  }
]
```

This allows Track A to understand why each supplied evidence item was retrieved without expanding its citation authority.

## Review-run identity and replay boundary

The canonical validated QuestionPlan is hashed with SHA-256. The review request binds:

```json
{
  "inputs": {
    "snapshot_hash": "...",
    "question_plan_sha256": "...",
    "question_plan": {
      "facts": [],
      "assumptions": [],
      "issues": [],
      "legal_anchors": []
    },
    "retrieval_lineage": []
  }
}
```

The deterministic reproducibility boundary starts **after** AI planning:

```text
same validated QuestionPlan
+ same evidence snapshot
+ same deterministic rule/math inputs
=> same deterministic retrieval/review preparation result
```

ERS does not claim that asking an external AI to plan the same question twice will necessarily produce the same QuestionPlan. Reproducibility is obtained by preserving and hashing the exact validated plan that was used.

## Failure states

Planner failure and evidence insufficiency are separate conditions.

| State | Meaning |
|---|---|
| `WAITING_QUESTION_PLAN` | Planner handoff has been prepared and external output is required. |
| `PLANNER_FAILED` | Planner output is missing, unreadable, invalid JSON, or violates the QuestionPlan contract. Retrieval has not started. |
| `RETRIEVAL_NO_EVIDENCE` | A valid QuestionPlan was executed, but deterministic retrieval returned no authoritative evidence. |
| `WAITING_TRACK_A` | A valid plan produced a prepared review run and Track A input is ready. |
| `ABSTAIN` | Existing final review logic determined that the available validated evidence is insufficient for a supported review result. |

`PLANNER_FAILED` must never be reported as `ABSTAIN` or `RETRIEVAL_NO_EVIDENCE`.

## Regression scope for Issue #112

Issue #112 originated from this question:

```text
에어컨 등 가전제품 설치기준 알려줘
```

The regression corpus intentionally does not contain that complete sentence. The validated fixture plan instead produces bounded searches such as:

```text
가전제품 설치기준
에어컨 설치기준
에어컨 실외기 설치
```

The integration matrix also includes three simple, three intermediate, and three complex synthetic questions. These fixtures validate question preservation, number/negation preservation, issue dependency structure, bounded search generation, evidence retrieval, lineage, and Track A plan binding. They do not encode or test a real legal conclusion.
