# Evidence-First Regulatory Review System Design

## Purpose

Build an API-free, file-based regulatory and design-review system for Codex Desktop and ChatGPT web. The system presents all relevant evidence and deterministic engine outputs; a human reviewer owns the final decision.

## Non-Negotiable Principles

1. **Human decision ownership:** machine outputs never populate the final decision.
2. **Complete review context:** every machine evaluation includes source location, governing clause, calculation trace, confidence basis, exceptions, and conflicts.
3. **Parse Engine ownership:** source bytes, raw parser records, page geometry, coordinates, tables, and visual assets are deterministic evidence. LLMs may flag anomalies but never overwrite raw evidence.
4. **Math Engine ownership:** all arithmetic, rounding, comparisons, and display values come from versioned deterministic formulas. LLMs do not calculate.
5. **Rule-as-Code:** approved rules are versioned executable JSON; identical inputs and versions produce identical machine evaluations.
6. **Citation-enforced Hybrid RAG:** factual claims must resolve to document, revision, page, element ID, bbox, and source hash.
7. **LLM abstention:** incomplete, conflicting, stale, unsupported, or weak evidence produces `ABSTAIN` and a human-review handoff.

## Runtime Boundary

The project code performs no OpenAI API or remote service calls. Codex Desktop or ChatGPT web supplies two separate LLM passes using generated input bundles. Deterministic validators decide whether those outputs may enter a final review packet.

## Canonical Status Values

- Rule: `SATISFIED`, `NOT_SATISFIED`, `INDETERMINATE`, `NOT_APPLICABLE`, `ENGINE_ERROR`
- Finalizer: `READY_FOR_HUMAN_REVIEW`, `ABSTAIN`
- Human decision: `SATISFIED`, `NOT_SATISFIED`, `CONDITIONAL`, `ADDITIONAL_REVIEW_REQUIRED`

## Data Flow

```text
Question + project inputs
  -> input validation
  -> structured + FTS + relation retrieval
  -> citation-resolved evidence
  -> Math Engine
  -> Rule Engine
  -> Track A explanation
  -> Track B audit
  -> deterministic confidence
  -> abstention gates
  -> immutable review packet
  -> separate human decision record
```

## Confidence Policy V1

| Factor | Weight |
|---|---:|
| source completeness | 0.20 |
| traceability | 0.15 |
| parse quality | 0.10 |
| human review status | 0.10 |
| rule coverage | 0.15 |
| input completeness | 0.15 |
| calculation validity | 0.05 |
| Track B agreement | 0.05 |
| source freshness | 0.03 |
| unresolved conflict factor | 0.02 |

- `HIGH`: score >= 0.90 and no hard gate fails
- `MEDIUM`: 0.70 <= score < 0.90 and no hard gate fails
- `LOW`: score < 0.70

Hard gates override the score: missing required input, uncited/unresolved claim, unapproved rule, Math Engine error, source hash mismatch, unresolved conflict, Track B rejection, machine-set human decision, or numeric value not registered by Math Engine/source evidence.
