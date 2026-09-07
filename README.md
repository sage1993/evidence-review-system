# Evidence Review System

Evidence Review System (ERS) is an offline, evidence-first review runtime for
turning user-provided PDFs and images into traceable local evidence, running
formal questions, and presenting the result for a separate human decision.

## Overview

The current review pipeline is:

```text
PDF or image
→ source/hash binding and immutable parser or drawing artifacts
→ evidence.sqlite for parser-ready reference evidence
→ active Review Workspace binding
→ external AI Question Planner
→ fail-closed QuestionPlan validation
→ deterministic retrieval and review preparation
→ Track A explanation and validation
→ independent Track B audit and validation
→ final-review-packet.json and review.html
→ protected Review Workspace
→ separate append-only human decision
```

The Python runtime does not call a model API. Codex supplies Question Planner,
Track A, and Track B outputs at explicit file handoffs; the runtime validates
them before the workflow advances. Planner output structures evidence search;
it is not evidence and cannot create a legal, compliance, or eligibility
conclusion.

## Core guarantees

- Original source bytes, SHA-256, document/revision/page identity, and
  bbox/geometry provenance remain bound to evidence.
- Canonical filesystem trust and verified regular-file boundaries reject unsafe
  paths, symlinks/reparse points, stale artifacts, and mismatched ownership at
  protected artifact boundaries.
- Parser records, retrieval, calculations, rules, and external track outputs
  are validated before they can contribute to the review packet.
- Missing or invalid planner/parser output, stale artifacts, hash mismatches,
  missing approved engine inputs, and failed validation stop the workflow
  fail-closed.
- Protected presentation and page-image delivery use a tokenized loopback
  server. Human decisions are packet-bound, create-only, append-only records;
  they do not mutate the machine packet or evidence.

Detailed contract and offline-boundary rules are in the
[documentation index](docs/README.md).

## Installation

Current package version: `0.2.0`
Supported Python: `>=3.13,<3.14`

On Windows, create an isolated Python 3.13 environment from the repository
root:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\python.exe -m evidence_review --version
```

PDF preparation requires a supported local parser, currently OpenDataLoader
PDF (`opendataloader-pdf`), unless an already verified parser artifact is
provided.

Runtime dependencies are constrained to `pypdf>=6.17,<7`,
`pypdfium2>=5.12,<6`, and `Pillow>=12,<13`.

## Quick start

### Parse a PDF

Use the repository-local `$ERS_PDF` workflow for a PDF that is intended to be
searchable reference evidence, such as a law, standard, report, or guideline:

```text
$ERS_PDF 이 PDF를 검색 근거자료로 준비해줘
```

This workflow preserves the source, validates parser/source binding and
reproducibility, builds source-batch v2 and `evidence.sqlite`, verifies the
required revision page-image cache, and binds the exact ready workspace. A
PDF supplied to be visually inspected as a drawing follows the case-visual
path in `$ERS_REVIEW` instead of being treated as reference corpus.

### Run a review

After reference evidence is prepared and bound, use `$ERS_REVIEW` for every
natural-language question:

```text
$ERS_REVIEW 이 문서가 해당 기준을 충족하는지 근거 페이지와 함께 검토해줘
```

There is no quick-answer or direct whole-sentence retrieval bypass. The
formal flow validates the active workspace, prepares a conclusion-free
QuestionPlan, retrieves bounded evidence, validates Track A, independently
audits Track B, and only then publishes the final review packet and HTML.
Users do not hand-author QuestionPlan, query bundles, review requests, track
handoff metadata, packet hashes, or timestamps.

## Review Workspace

The reviewer-facing workspace prioritizes:

1. result status and a concise conclusion;
2. source evidence with document, page, quote, bbox, and verified page image;
3. additional review only when missing, conflicting, exceptional, or
   abstention information exists; and
4. the human decision and notes.

The protected browser route is tokenized and loopback-only. Archival
`review.html` can be opened as a file, but its downloaded decision envelope
must go through the approved import path to persist an append-only decision.
Internal IDs, hashes, confidence details, and raw audit data remain available
under collapsed audit details.

## What `READY_FOR_HUMAN_REVIEW` means

`READY_FOR_HUMAN_REVIEW` means the machine review packet is ready for a person
to inspect. It does not mean approved, compliant, legally correct, or finally
decided. The machine packet keeps `human_decision` separate and null; a valid
reviewer decision is stored as a new packet-bound record.

## Current limitations

- The runtime is offline except for protected loopback communication. External
  AI work happens only at explicit file handoffs.
- A reference-document review cannot proceed without a valid active workspace,
  parser-ready evidence, and required verified page-image cache. Drawing and
  supporting-image review can remain blocked until visual analysis and source
  identity checks are complete.
- Calculations and rule outcomes must come from approved deterministic engine
  artifacts; the runtime does not infer them from prose or an image.
- Browser QA, release artifact validation, and human process attestation are
  separate acceptance gates. An unexecuted gate is `NOT_RUN`, not PASS.

## Release authority

The current release acceptance authority is
[docs/MANUAL_ACCEPTANCE_POLICY.md](docs/MANUAL_ACCEPTANCE_POLICY.md). Use the
following commands for release validation and build:

```powershell
py -3.13 scripts/validate_release.py $WORKSPACE
py -3.13 scripts/build_release.py $WORKSPACE <output>
```

Retired and legacy validator boundaries are documented in the
[documentation index](docs/README.md); they are not part of the current release
path.

## Developer verification

Run from a clean checkout at the exact HEAD with Python 3.13:

```powershell
py -3.13 -m evidence_review documentation validate --repository-root . --config documentation-integrity.json --output .verification/documentation-integrity.json
py -3.13 -m pytest -v
py -3.13 -m ruff check src tests web_runtime
py -3.13 -m mypy src
py -3.13 -m mypy --platform win32 src
py -3.13 -m compileall -q src scripts web_runtime tests
```

The documentation integrity command validates current links, headings,
document classification, and documented CLI/script paths without executing
the documented commands. Full acceptance also includes the applicable focused
review suites, protected-browser and archival decision paths, release smoke
checks, and manual viewport/accessibility QA. Report every unexecuted gate as
`NOT_RUN` and report GitHub Actions separately from local verification.

## Documentation

Use [docs/README.md](docs/README.md) as the documentation entrypoint. It maps
current authority, architecture/contracts, operations, migration compatibility,
acceptance records, and historical implementation plans. Active Codex
instructions are under [.agents/skills/README.md](.agents/skills/README.md).

## Security and data handling

Do not commit proprietary or customer PDFs, parser output derived from
restricted documents, evidence databases, page-image caches, human-decision
records, credentials, tokens, private URLs, or private keys. See
[Offline Execution Boundary](docs/OFFLINE_EXECUTION.md) and the repository
[SECURITY.md](SECURITY.md) for the detailed boundaries.

## License

Evidence Review System is licensed under the [Apache License 2.0](LICENSE).
