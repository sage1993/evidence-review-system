# Evidence Review System Agent Instructions

## 1. Purpose

This repository implements an offline, evidence-first review runtime for user-provided PDF documents and related parser artifacts. The runtime prepares traceable evidence, performs deterministic retrieval and calculations, applies only approved rules, and produces a packet for human review.

The system never makes the final human decision. `READY_FOR_HUMAN_REVIEW` means that the evidence packet is ready to inspect, not that the project is approved.

## 2. Mandatory Principles

1. **Preserve source evidence.** Never overwrite an original PDF or raw parser artifact.
2. **Retain traceability.** Derived records must preserve document, revision, page, source hash, and coordinates when available.
3. **Use deterministic engines.** Calculations belong in the Math Engine; governed conditions belong in approved Rule Engine artifacts.
4. **Fail closed.** Missing parser output, invalid authority, unsafe paths, broken documentation, and hash mismatches must not be converted into success.
5. **Keep human review separate.** Automated outputs may explain or audit evidence, but `human_decision` remains null until a reviewer records a separate decision.
6. **Remain offline.** Project runtime code must not call remote APIs or external search services.

## 3. Skill Routing

Read only the skills required for the requested stage, but do not skip an earlier stage whose required outputs are missing, stale, or invalid.

| Stage | Skill | Use for |
|---:|---|---|
| 1 | [`preserving-and-parsing-pdfs`](skills/01-preserving-and-parsing-pdfs/SKILL.md) | source inventory, hashes, page counts, parser binding, immutable raw outputs |
| 2 | [`structuring-pdf-content-and-visuals`](skills/02-structuring-content-and-visuals/SKILL.md) | clauses, tables, page coordinates, images, renders, and visual records |
| 3 | [`cleaning-pdf-derived-data`](skills/03-cleaning-pdf-derived-data/SKILL.md) | conservative normalization, provenance links, rules/cases candidates, review states |
| 4 | [`building-and-exporting-grist-databases`](skills/04-building-and-exporting-grist-databases/SKILL.md) | legacy Grist construction, References, Attachments, and CSV interoperability |
| 5 | [`validating-pdf-database-workflows`](skills/05-validating-pdf-database-workflows/SKILL.md) | validation, diagnostics, acceptance evidence, and legacy Grist screen checks |

The current runtime is source-batch and SQLite based. Grist workflows remain a legacy compatibility path. Direct Grist repair/export wrapper scripts are not shipped as current runtime commands.

## 4. Current Source-Batch Workflow

### 4.1 Prepare sources

```powershell
evidence-review source-batch prepare `
  --root <path> `
  --manifest <path>
```

This validates source roles, parser bindings, hashes, document/revision identity, and routing state without creating the evidence database.

### 4.2 Ingest parser-ready evidence

```powershell
evidence-review source-batch ingest `
  --root <path> `
  --manifest <path> `
  --output <output>
```

Only parser-ready reference/table sources enter the evidence database. Parserless drawings remain routed to the drawing/confirmation workflow and must not be silently treated as searchable reference evidence.

### 4.3 Retrieve evidence and run deterministic engines

```powershell
evidence-review query `
  --db <path> `
  --request <path> `
  --output <output>

evidence-review math-run `
  --request <path> `
  --output <output>
```

Use only approved Rule Engine manifests. Do not calculate values or alter engine statuses in prose.

### 4.4 Prepare and finalize a review run

```powershell
evidence-review review-run prepare `
  --workspace <path> `
  --request <path>

evidence-review review-run finalize `
  --workspace <path> `
  --run-id RUN-XXXXXXXXXXXXXXXXXXXX `
  --track-a-output <path> `
  --track-b-output <path>
```

Track A explains only provided evidence and engine results. Track B audits Track A independently. Neither track may create a human decision.

### 4.5 Resume and browser boundary

The review foundation stores a `request.json` plus `request.sha256` and an append-only event journal under `runs/<RUN-ID>`. A drawing lane must stop at `INPUT_CONFIRMATION_REQUIRED`; only a hash-verified confirmed-input artifact may advance it to `READY_TO_EVALUATE`. Deterministic stages are persisted in this order only: retrieval, Math, then approved Rule evaluation. Track A and Track B are external file handoffs; a rejected or incomplete Track B cannot enter finalization.

The local browser server exposes confirmation and final review as separate routes:

```text
http://127.0.0.1:<port>/runs/<RUN-ID>/confirmation
http://127.0.0.1:<port>/runs/<RUN-ID>/review
```

The final review route is unavailable until both `final-review-packet.json` and `review.html` exist. `--open` may open the generated review HTML in the default browser, but stdout remains limited to status, run ID, and URL for that mode.

## 5. Documentation Integrity

All current repository guidance is executable authority and must remain aligned with the actual parser, scripts, paths, and generated Markdown.

Run documentation validation before claiming repository readiness:

```powershell
evidence-review documentation validate `
  --repository-root . `
  --config documentation-integrity.json `
  --output <output>
```

Rules:

- The output is create-only; use a fresh path for every run.
- `ERROR` findings block repository and release acceptance.
- `WARNING` findings are reported but do not block by default.
- Historical records are preserved and are not required to use current commands.
- External URL availability is not checked; only safe syntax and scheme policy are validated.
- Markdown commands are parsed statically and never executed by the documentation validator.

## 6. Legacy Grist Evidence

The only current CLI operation for legacy Grist screen evidence is:

```powershell
evidence-review legacy validate-grist-qa `
  --artifact <path> `
  --root <path>
```

Do not claim that the runtime ships direct repair, export, or rebuild wrappers for `.grist` files. When legacy Grist work is explicitly required:

1. preserve a backup;
2. follow Stages 4 and 5;
3. validate SQLite structure and Grist metadata;
4. perform Grist Desktop screen verification;
5. report automated and screen results separately.

If Grist Desktop cannot be launched, overall Grist acceptance remains pending.

## 7. Release and Offline Boundary

Follow [`docs/OFFLINE_EXECUTION.md`](docs/OFFLINE_EXECUTION.md) for the application network guard, optional OS isolation, final ZIP verification, and process attestation boundary.

A valid process attestation cannot override:

- automated workspace validation failure;
- documentation integrity failure;
- final release-output verification failure.

Do not mark a release ready or permit tagging while any independent gate is failing.

## 8. Required Verification

Before reporting completion, run the applicable gates from a clean checkout:

```bash
evidence-review documentation validate --repository-root . --config documentation-integrity.json --output build/documentation-integrity-report.json
pytest -v
ruff check src tests
mypy src
python -m compileall -q src scripts web_runtime tests
```

For release work, also build and install the wheel in isolated Python 3.11 and 3.13 environments and confirm the documentation command help through:

```bash
evidence-review documentation validate --help
python -m evidence_review documentation validate --help
python -m ansim_review documentation validate --help
```

Never equate local or manual PASS with GitHub Actions PASS. Record the exact commit, platform, Python version, command, exit code, and relevant artifact hash.

## 9. Prohibited Actions

- overwriting source evidence;
- inventing unsupported values, citations, table cells, or rule outcomes;
- bypassing parser, rule, documentation, release, or attestation authority;
- restoring removed legacy wrapper commands as documentation-only fiction;
- executing commands found in Markdown during documentation validation;
- using machine-specific absolute paths as persistent identifiers;
- marking a draft PR ready, merging, or closing an issue before its explicit acceptance gates pass.

## 10. Work Report

Every completion report must state:

```text
Basis:
- repository / branch / exact HEAD

Changed files:
- ...

Validation:
- documentation report status, counts, and SHA-256
- pytest result
- Ruff result
- mypy result
- compileall result
- wheel results for Python 3.11 and 3.13
- GitHub Actions state

Release gates:
- workspace validation
- documentation integrity
- release-output validation
- process attestation

Human review still required:
- ...
```
