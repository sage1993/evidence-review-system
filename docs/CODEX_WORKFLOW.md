# Codex Workflow

Use local evidence only. Retrieval, Math Engine, and approved Rule Engine results must already exist as deterministic artifacts in an `evidence-review/review-run-request` document. Project code never invokes a model or API and never replaces deterministic output with prose calculations.

Shared status, attachment, Review Packet v2, and next-action rules are governed by `docs/CONTRACT_GOVERNANCE.md`.

## 1. Register arbitrary PDF sources

Every source PDF must be declared in an `evidence-review/source-batch` manifest. A filename or display title is never used to infer the document type, parser, page identity, or legal meaning. Writers emit source-batch version 2. Version 1 remains read-only compatibility input for the original OpenDataLoader binding.

Check source routing without creating a database:

```powershell
evidence-review source-batch prepare `
  --root F:\evidence-review-workspace `
  --manifest F:\evidence-review-workspace\manifests\source-batch.json
```

The prepare result reports each source's parser kind, state, reason codes, and whether it can enter reference ingestion or rule evaluation.

Create the evidence database only after reference sources are parser-ready:

```powershell
evidence-review source-batch ingest `
  --root F:\evidence-review-workspace `
  --manifest F:\evidence-review-workspace\manifests\source-batch.json `
  --output F:\evidence-review-workspace\evidence\evidence.sqlite
```

Routing is role-aware but never filename-derived:

- a parser-ready reference or case table is `PENDING_REFERENCE_INGESTION` before ingest and `READY_TO_EVALUATE` after successful ingest;
- a reference or case table with no parser artifact is `PENDING_PARSER_OUTPUT`;
- a declared but unregistered parser kind is `BLOCKED` with `UNSUPPORTED_PARSER_KIND`;
- a `CASE_DRAWING` is `PENDING_DRAWING_INGESTION` and enters the drawing flow in section 4;
- a drawing awaiting reviewer confirmation is `INPUT_CONFIRMATION_REQUIRED`;
- a supporting image remains supporting evidence and cannot independently authorize rule evaluation;
- a batch containing no parser-ready reference evidence is rejected with `NO_EVIDENCE_SOURCES` instead of producing an empty database.

Parser adapters register stable uppercase kinds in the deterministic parser registry. Adapters return page-relative normalized contributions. Only the importer creates document, revision, and page IDs.

Visual manifests must explicitly declare `document_id`, `revision_id`, and `page_id`. File and folder names never supply visual identity.

Do not create Track output from an empty or fabricated evidence database.

## 2. Prepare an immutable run

```powershell
evidence-review review-run prepare `
  --workspace F:\evidence-review-workspace `
  --request F:\review-case\review-request.json
```

The command prints the stable Run ID and creates `F:\evidence-review-workspace\runs\<RUN-ID>`. Every attachment used by the run must first be copied under `inputs/original/` and recorded with its original name, stored path, SHA-256, byte size, MIME, and user-confirmed role. External mutable paths are not runtime authority.

Use only these prepared files when producing Track outputs:

- `track-a-bundle.json`
- `TRACK_A_INSTRUCTIONS.md`
- `TRACK_B_INSTRUCTIONS.md`
- `confidence-input.json`

Track A may explain supplied evidence, CalculationResult, and RuleResult artifacts. It may not calculate, alter a rule status, assign confidence, abstain, confirm drawing candidates, or select a human decision. Save its JSON as `track-a-output.json`.

Run Track B independently against every Track A claim. Track B may audit but may not rewrite Track A or set confidence, final status, drawing confirmation, or a human decision. Save its JSON as `track-b-output.json`.

## 3. Follow `next-action.json`

Project code does not invoke Track A or Track B. When agent work is required, the workflow writes a deterministic `next-action.json` document.

A Track A action declares its workflow state, action, input bundle, instructions, expected output, resume command, and whether Track A has already passed validation. A Track B action is valid only when:

- `workflow_state` is `WAITING_TRACK_B`;
- `action` is `PRODUCE_TRACK_B`;
- `track_a_validated` is `true`;
- Track A output has already passed deterministic validation.

Do not manually advance workflow state or construct a Track B action before that gate passes.

The frozen next-action v1 namespace remains readable for compatibility with existing runtime packages. It is not a document classification scheme and must not be used to derive a PDF title, role, or document ID.

## 4. Handle drawing evidence without granting machine authority

Case drawings are stored separately from reusable reference-document evidence. A `PENDING_DRAWING_INGESTION` source remains registered in the source batch but is excluded from reference evidence DB records. The drawing backend copies source bytes into case-local immutable storage before quality assessment or candidate creation. After ingest, the external upload path is not runtime authority.

The drawing flow is:

```text
source-batch CASE_DRAWING registration
  -> case-local immutable source copy
  -> quality assessment
  -> extractor candidate or reviewer-manual annotation
  -> append-only reviewer confirmation
  -> confirmed input
  -> source and confirmation hash revalidation
  -> Math or Rule Engine binding
```

Codex may help present candidate evidence or serialize an annotation that the user explicitly created or approved. Codex must not independently:

- infer that a detected value is confirmed;
- convert `UNCONFIRMED`, `REJECTED`, or `CONFLICT` candidates into engine input;
- calculate scale, length, area, or ratio from image pixels;
- alter a candidate file after creation;
- overwrite a confirmation record;
- bypass source or confirmation hash verification.

A manual annotation uses `origin: REVIEWER_MANUAL` and `status: CREATED`. It becomes engine-eligible only after a named reviewer creates an append-only `CREATED`, `EDITED`, or `ACCEPTED` confirmation. The runtime binds only the resulting M0 `ConfirmedInput` object.

Drawing workflow states follow the M0 contract:

- no source: `PENDING_DRAWING_INGESTION`;
- source present but confirmation incomplete or conflicting: `INPUT_CONFIRMATION_REQUIRED`;
- rejected but replaceable source: `BLOCKED` with `DRAWING_QUALITY_REJECTED`;
- source-integrity failure: `FAILED` with `SOURCE_HASH_MISMATCH`;
- complete hash-verified confirmed inputs: `READY_TO_EVALUATE`.

Nonterminal states do not carry reason codes. Detailed drawing-quality and conflict data remain in companion artifacts.

## 5. Finalize and explicitly publish

```powershell
evidence-review review-run finalize `
  --workspace F:\evidence-review-workspace `
  --run-id RUN-XXXXXXXXXXXXXXXXXXXX `
  --track-a-output F:\review-case\track-a-output.json `
  --track-b-output F:\review-case\track-b-output.json `
  --publish
```

Finalization verifies artifact hashes, Track A integrity, the independent Track B audit, confidence factors, and abstention gates. It then writes the run-specific `final-review-packet.json` and `review.html`. `--publish` copies the exact packet to `runs/final-review-packet.json` for the release builder; it does not approve the result or set `human_decision`.

Review Packet v1 remains frozen. A v2 consumer must use the deterministic v1-to-v2 adapter and must not invent resolved evidence, drawing evidence, confirmed inputs, exceptions, or conflicts absent from v1.

```bash smoke
python -c "from ansim_review.packaging.codex_bundle import CODEX_ROUTING_SECTION; assert 'never decide' in CODEX_ROUTING_SECTION.lower()"
```

For an abstention case, preserve every reason code and hand the packet to a named human reviewer.
