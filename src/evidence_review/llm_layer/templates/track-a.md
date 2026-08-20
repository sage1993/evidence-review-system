# Track A — Evidence-Only Explanation

Use only the supplied evidence, validated case-visual candidates, CalculationResult, and RuleResult artifacts.
Return JSON with exactly: `run_id`, `claims`, `citations`, `missing_inputs`,
`exceptions`, `conflicts`, and `explanation`.

Do not calculate, change a rule status, assign confidence, abstain, or set a
human decision. Every factual claim must cite supplied citation IDs.

When `inputs.question_plan` is present, organize the explanation against its
validated issues and preserve its facts, assumptions, and dependency structure.
Do not create replacement issues or silently reinterpret the original question.
Legal anchors in the plan are planning context only: an anchor with
`source=planner` is a retrieval hypothesis, not legal authority. Treat a legal
anchor as authoritative only when the supplied evidence supports it.

When evidence items contain `issue_ids`, every claim must contain a non-empty
`issue_ids` array. Claim issue IDs must be copied from the supplied issue-aware
evidence. Every citation used by a claim must share at least one issue ID with
that claim. Do not cite evidence from another issue merely because the citation
is valid or topically adjacent. A claim without issue lineage, an unknown issue,
or a cross-issue citation is invalid.

When `inputs.retrieval_lineage` is present, use it only to understand which
validated issue/search request led to each cited evidence item. Lineage does not
increase evidence authority or permit citation IDs outside the supplied bundle.

## Case visual evidence

When `inputs.case_visual_context.visual_status` is
`VISUAL_ANALYSIS_VALIDATED`, claims may include an optional
`drawing_candidate_ids` array. Use only candidate IDs present in
`inputs.case_visual_context.drawing_candidates`, and only when that candidate's
`candidate_lineage.issue_ids` overlaps the claim's `issue_ids`.

Drawing candidates are case-specific visual facts. They are **not** legal or
regulatory authority and do not replace `citation_ids`. A claim that references
a drawing candidate must still satisfy the normal citation requirements.

Do not treat `UNCONFIRMED` drawing candidates as deterministic measurements or
as Math/Rule inputs. Do not promote visible text or dimensions into new numeric
claims unless the exact numeric token is independently allowed by the normal
citation/CalculationResult rules.

If `visual_status` is not `VISUAL_ANALYSIS_VALIDATED`, do not reference drawing
candidates.

## Numeric claim rules

Every numeric value in claim text must appear in that claim's `numeric_tokens`
array in exactly the same source order and spelling. Use only canonical ASCII
numeric forms:

- integer: `0`, `12`, `-12`, `+3`
- grouped integer: `1,234`
- decimal: `0.5`, `12.50`
- percentage: `9.375%`, `12.50%`

Numeric values must be copied exactly from cited source text or from a linked
successful CalculationResult. Do not add or remove commas, signs, decimal
zeros, or percent signs.

The following forms are unsupported and must not appear in a claim:

- scientific notation such as `1e3` or `1E-3`
- leading-dot decimals such as `.5`; use an exact deterministic `0.5` result
  only when that representation exists in evidence or a CalculationResult
- underscore separators such as `1_000`
- malformed comma groups such as `12,34` or `1,23,456`
- Unicode numeric characters such as `½`, `１２３`, superscripts, or circled
  numbers

Do not normalize an unsupported source form yourself. A deterministic parser or
Math Engine result must provide an accepted representation before Track A may
use it.
