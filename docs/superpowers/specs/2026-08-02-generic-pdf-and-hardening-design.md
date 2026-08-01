# Generic PDF Intake and Trust-Boundary Hardening Design

## 1. Purpose

The system must accept arbitrary user-provided PDFs whose filenames, titles, structure, and subject matter change from run to run. The former Ansim housing-standard workspace is a sample migration source, not the product model.

This design removes sample-name assumptions from new ingestion and output contracts while preserving legacy artifacts through explicit read-only compatibility paths.

## 2. Scope

This implementation slice covers:

1. generic source-batch contracts for arbitrary PDFs and parser artifacts;
2. stable document identity derived from explicit metadata or source bytes, never special filenames;
3. removal of `law-1`, `law-2`, `LAW1`, and `LAW2` special handling;
4. configurable source and export locations instead of fixed numbered folders;
5. user-facing product identifiers based on `evidence-review`;
6. rule-promotion path containment;
7. rule expression/input reference validation;
8. Run ID coverage for all deterministic decision inputs.

The following remain separate migrations because they require independent review gates:

- evidence database page-FK migration: issue #19;
- release acceptance assurance model: issue #20;
- full internal Python package rename from `ansim_review`: follow-up under issue #22.

## 3. Naming and Compatibility

### 3.1 New identifiers

New artifacts use:

- CLI: `evidence-review`;
- JSON format prefix: `evidence-review/`;
- default database file: `evidence.sqlite`;
- workspace examples: `evidence-review-workspace`;
- release name: package version or configured release ID.

### 3.2 Legacy identifiers

Existing `ansim/*` files may only enter through explicitly named legacy adapters. New runs must not emit `ansim/*` formats.

The internal `ansim_review` import namespace remains temporarily available in this slice to avoid a repository-wide rename mixed with trust-boundary changes. It is an implementation detail and must not be presented as the product name.

## 4. Generic Source-Batch Contract

A source batch is a deterministic manifest:

```json
{
  "format": "evidence-review/source-batch",
  "version": 1,
  "sources": [
    {
      "source_path": "inputs/original/site-policy.pdf",
      "role": "REFERENCE_DOCUMENT",
      "document_id": null,
      "display_title": "Site policy",
      "parser": {
        "kind": "OPENDATALOADER_JSON",
        "artifact_path": "inputs/parser/site-policy.json"
      }
    }
  ]
}
```

### 4.1 Identity rules

- `source_path` and parser artifact paths are safe relative paths under the batch root.
- Source bytes are hashed before any identifier is created.
- An explicit `document_id` must pass the shared safe-ID validator.
- Without an explicit ID, use `DOC-` plus the first 20 uppercase hex characters of the source SHA-256.
- `revision_id` is `<document_id>-<first 12 lowercase source-hash characters>`.
- `display_title` is presentation metadata and never controls identity.
- Same bytes with different filenames resolve to the same auto document ID and revision ID.
- Same filename with different bytes resolves to a different auto document ID.

### 4.2 Parser handling

Parser adapters are selected by `parser.kind`, not by filename.

Initial supported kind:

- `OPENDATALOADER_JSON`

No parser artifact means the source remains registered but is not eligible for evidence ingestion. The caller receives a deterministic `PENDING_PARSER_OUTPUT` reason rather than an inferred or fabricated parse result.

## 5. Configurable Workspace Import

The generic importer consumes a source-batch manifest and optional reviewed-data locations:

```python
import_source_batch(
    batch_root: Path,
    manifest_path: Path,
    output_db: Path,
    reviewed_exports: Path | None = None,
    visual_manifests: Path | None = None,
) -> ImportReport
```

The importer does not assume numbered folders. Legacy numbered-folder import remains in a legacy module and converts its discovered files into the generic source-batch model before ingestion.

Visual manifests must declare `document_id`. Filename-based law-number inference is removed.

## 6. Rule Trust Boundary

### 6.1 Safe identifiers

Rule IDs and versions are validated before path construction. A promoted rule path must resolve to exactly one file directly below `rules/approved`.

### 6.2 Expression references

The loader collects input references and calculation references from the validated expression.

- Every input reference must exist in `input_schema`.
- Calculation nodes are validated structurally during load.
- The evaluator validates only calculation results referenced by the expression.
- Unrelated calculation results cannot change a rule result.

## 7. Run Identity

The Run ID is derived from the complete normalized deterministic review request, including:

- question;
- project inputs;
- evidence documents;
- finalized calculations;
- finalized rules;
- approved rule result IDs;
- confidence inputs.

Key ordering and input list ordering are normalized before hashing. Operational paths and timestamps are excluded.

## 8. Error Handling

- Unsafe paths: `ValueError` before file access.
- Missing source PDF: `FileNotFoundError`.
- Missing parser output: deterministic pending result, not an empty evidence snapshot.
- Duplicate explicit document ID with different source bytes in one batch: `ValueError`.
- Duplicate source bytes: deduplicate to one source entry.
- Parser metadata/source mismatch: `ValueError`.
- Unknown parser kind: `ValueError`.
- Legacy format supplied to a new-format decoder: reject unless the legacy adapter is explicitly used.

## 9. Testing Strategy

Fixtures must not use `law-1` or `law-2` as privileged names.

Required cases:

1. two unrelated policy PDFs;
2. same filename with different bytes;
3. different filenames with identical bytes;
4. explicit document ID;
5. unsafe source and parser paths;
6. missing parser artifact;
7. visual manifest without document ID;
8. rule path traversal strings;
9. undeclared rule input reference;
10. unrelated failed calculation result;
11. Run ID changes when approvals or confidence change.

## 10. Completion Criteria

- New source-batch, review-run, and user-facing documentation use `evidence-review` identifiers.
- No new artifact emits `ansim/*`.
- Generic ingestion succeeds without sample document names or numbered folders.
- The former housing-standard material is an ordinary fixture only.
- Issues #17, #18, and #21 are closed by verified tests.
- Issues #19 and #20 remain explicitly tracked until their separate migrations pass.