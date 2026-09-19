# Track B — Independent Audit

Read the immutable Track B input bundle and audit every Track A claim ID exactly once. Do not rewrite Track A and do not set confidence, abstention, final status, or a human decision.

Write only `track-b-output.json` using this exact shape:

```json
{
  "run_id": "<exact run id>",
  "audited_question": "<exact question copied from the immutable input bundle>",
  "question_responsiveness": "PASS|FAIL|NOT_VERIFIED",
  "required_facet_completeness": "COMPLETE|INCOMPLETE|NOT_APPLICABLE",
  "claim_audits": [
    {
      "claim_id": "<exact Track A claim id>",
      "disposition": "ACCEPT|REJECT|INCOMPLETE",
      "finding_codes": [],
      "notes": ""
    }
  ],
  "overall_disposition": "ACCEPT|REJECT|INCOMPLETE"
}
```

Rules:

- Copy the immutable input question exactly into `audited_question`; do not answer a different question.
- Set `question_responsiveness` to `PASS` only when the audit actually addresses that exact question. Use `FAIL` when it addresses another question or otherwise does not answer the requested question. Use `NOT_VERIFIED` when responsiveness cannot be established.
- Copy the required-facet status from the immutable input bundle. `NOT_APPLICABLE` is allowed only when the bundle declares no required facet obligation. `INCOMPLETE` must never be reported as a complete acceptance.
- Audit every Track A `claim_id` exactly once. Do not omit, duplicate, invent, or rename claim IDs.
- `run_id` must exactly match the input bundle.
- Allowed dispositions are `ACCEPT`, `REJECT`, and `INCOMPLETE`.
- Allowed finding codes are `MISSING_EXCEPTION`, `CITATION_MISMATCH`, `UNSUPPORTED_CLAIM`, `CALCULATION_MISMATCH`, `RULE_STATUS_MISMATCH`, `FINAL_DECISION_LANGUAGE`, and `SOURCE_CONFLICT`.
- An `ACCEPT` audit must have an empty `finding_codes` array.
- A `REJECT` or `INCOMPLETE` audit may use only the allowed finding codes that actually apply.
- `notes` must be a JSON string. Use an empty string when no note is needed.
- Derive `overall_disposition` deterministically: any `REJECT` claim makes the overall disposition `REJECT`; otherwise any `INCOMPLETE` claim makes it `INCOMPLETE`; otherwise it is `ACCEPT`.
- If Track A contains no claims, `claim_audits` must be empty and `overall_disposition` must be `INCOMPLETE`.

Forbidden top-level fields include `rewritten_claims`, `claims`, `human_decision`, `final_decision`, `confidence`, and `abstention`.

Do not write explanatory prose outside the JSON output.
