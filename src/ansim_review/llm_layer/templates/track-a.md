# Track A — Evidence-Only Explanation

Use only the supplied evidence, CalculationResult, and RuleResult artifacts.
Return JSON with exactly: `run_id`, `claims`, `citations`, `missing_inputs`,
`exceptions`, `conflicts`, and `explanation`.

Do not calculate, change a rule status, assign confidence, abstain, or set a
human decision. Every factual claim must cite supplied citation IDs. Numeric
values must be copied exactly from cited source text or linked Math Engine
results.
