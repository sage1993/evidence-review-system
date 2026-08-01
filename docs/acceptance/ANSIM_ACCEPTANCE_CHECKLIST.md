# Ansim v1.0 Human Acceptance Checklist

This checklist must be completed by a named human reviewer against the actual migrated Ansim Housing sources and rendered review packets. Automated tests cannot sign this gate.

For every item, record `PASS`, reviewer evidence such as document/page/run/file, and any notes:

1. `SOURCE_IDENTITY` — original PDF names, SHA-256 values, page counts, parser outputs, and migration inventory match.
2. `CITATION_PAGE_BBOX` — sampled factual claims open the correct document revision, page, evidence ID, source hash, and visible bbox.
3. `TABLE_AND_VISUAL_EVIDENCE` — sampled tables, crops, page renders, and composite diagrams match the source PDF without invented content.
4. `CALCULATION_TRACE` — substitutions, raw values, display values, comparisons, formula versions, and result hashes are correct.
5. `RULE_VERSION_AND_STATUS` — only approved active rules execute and sampled boundary/equality/indeterminate outcomes match the source-backed rule.
6. `TRACK_A_EXPLANATION` — Track A is explanatory only, contains resolved citations, and does not calculate or decide.
7. `TRACK_B_AUDIT` — every Track A claim is independently audited and rejection/incomplete findings are preserved.
8. `CONFIDENCE_FACTORS` — all ten factors, weights, contributions, sources, score, and level are visible and correct.
9. `ABSTENTION_BEHAVIOR` — missing input, unresolved citation, source conflict, engine errors, Track B rejection, and low confidence abstain with all applicable codes.
10. `HUMAN_DECISION_SEPARATION` — machine packets keep `human_decision: null`; reviewer identity, timestamp, signature, packet hash, and decision are stored separately.

The acceptance JSON must use format `ansim/human-acceptance`, version `1`, include the exact release candidate hash and packet hash, and contain all ten checks with non-empty evidence references. Do not create or copy a signature on behalf of a reviewer.
