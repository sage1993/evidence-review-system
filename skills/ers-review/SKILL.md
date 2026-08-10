---
name: ers-review
description: Use when a user invokes $ERS_REVIEW or asks Codex Desktop to answer a question from a parsed Evidence Review System workspace.
---

# ERS Review

## Overview

`$ERS_REVIEW` turns a natural-language question into an evidence-backed answer and opens the generated review HTML. The user should not have to write query JSON, run Math Engine commands, or assemble Track files manually.

## Required workflow

1. Locate the most recent ERS workspace produced by `$ERS_PDF`. If no parser-ready evidence database exists, stop and tell the user to run `$ERS_PDF` first. Do not parse a PDF or use repository samples silently during review.
2. Convert the user's question into a deterministic evidence request and run:

```powershell
evidence-review query --db <workspace>\evidence\evidence.sqlite --request <case>\evidence-query.json --output <case>\evidence-bundle.json
```

3. Use only returned citations and verified source records. If the question needs numbers, use an approved formula request and run:

```powershell
evidence-review math-run --request <case>\calculation-request.json --output <case>\calculation-result.json
```

Never calculate a new value in prose. Use only an approved Rule Engine manifest when a governed rule is required.
4. Prepare a review run with `review-run prepare`. Write Track A as an explanation of supplied evidence and engine results. Audit every Track A claim independently in Track B. Neither track may invent evidence, assign human confidence, or make a human decision.
5. Finalize only with both valid track outputs:

```powershell
evidence-review review-run finalize --workspace <workspace> --run-id <RUN-ID> --track-a-output <case>\track-a-output.json --track-b-output <case>\track-b-output.json --publish --open
```

For this user-facing shortcut, `--open` is mandatory. Do not treat browser opening as optional. Confirm that the run-specific `final-review-packet.json` and `review.html` both exist and that the open operation returned a local review URL. If either artifact or the browser URL is missing, report the run as incomplete; do not claim that the review screen was opened.

## Answer contract

Return a short Korean answer with these sections:

1. 결론 — say satisfied, not satisfied, or additional review required only when supported by the packet.
2. 근거 — document name, page, evidence ID, and source citation.
3. 검토 내용 — explain the relevant rule or calculation using recorded results.
4. 주의사항 — list missing, conflicting, unconfirmed, or abstained inputs.
5. 상세 화면 — give the local `review.html` path or URL and state that it was opened when `--open` succeeded.

## Safety rules

- `READY_FOR_HUMAN_REVIEW` means the packet is ready to inspect, not approved. `ABSTAIN` means the runtime preserved a reason for not concluding.
- Keep `human_decision` as `null`; a human decision belongs in the separate append-only workflow.
- Never invent text, tables, page numbers, coordinates, formulas, rule outcomes, or citations.
- Never turn a parser warning, unconfirmed drawing candidate, or missing input into a successful answer.
- Never treat a JSON file without the finalized `review.html` as a completed review.

## Common stop conditions

| Condition | Response |
|---|---|
| No parsed workspace | Ask the user to run `$ERS_PDF` first. |
| `PENDING_PARSER_OUTPUT` or `BLOCKED` | Report the exact state and reason; do not answer from memory. |
| `INPUT_CONFIRMATION_REQUIRED` | Explain that drawing confirmation is required before calculation. |
| Missing formula or approved rule | Return `ABSTAIN` or `BLOCKED` with the missing authority. |
| Track A/Track B rejection | Preserve the abstention reason and do not finalize as ready. |
| Missing packet, HTML, or open URL | Report incomplete finalization and do not claim the screen opened. |
