# Review Run Orchestration Design

## Goal

Add an operational `ansim-review review-run` workflow that creates a deterministic run directory, accepts externally generated Track A and Track B JSON, finalizes the machine review packet, renders reviewer HTML, and explicitly publishes one packet for the release builder.

## Constraints

- Project code performs no model or API calls.
- Track A and Track B remain untrusted, file-based inputs.
- Math and Rule Engine results remain deterministic authority artifacts; the orchestration layer must not recalculate or rewrite them.
- Every generated JSON file uses canonical UTF-8 bytes.
- Existing run directories and final packets are never overwritten.
- Machine packets always keep `human_decision` equal to `null`.
- Windows and POSIX paths must produce the same canonical run bytes.

## Approaches Considered

### 1. Monolithic command that invokes an LLM

Rejected. It would violate the offline and no-network boundary and would make Track A and Track B dependent on an API implementation.

### 2. Staged prepare/finalize workflow

Selected. `prepare` creates the trusted deterministic bundle and confidence input. ChatGPT Web or Codex produces Track A and Track B files outside project code. `finalize` imports those files, hashes the complete run manifest, invokes the existing finalizer, renders HTML, and optionally publishes the packet selected for release.

### 3. Manual directory assembly

Rejected. It is possible with the existing finalizer but error-prone: hashes, required artifact names, run IDs, and publication paths can be assembled incorrectly.

## Command Surface

### Prepare

```powershell
ansim-review review-run prepare `
  --workspace F:\ansim-workspace `
  --request F:\ansim-case\review-request.json
```

The request format is `ansim/review-run-request`, version `1`, and contains:

- `question`: non-empty string.
- `inputs`: JSON object.
- `evidence`: Track A evidence excerpts containing canonical citations and text.
- `calculations`: complete deterministic `CalculationResult` documents.
- `rules`: complete deterministic `RuleResult` documents.
- `approved_rule_result_ids`: approved rule-result IDs.
- `confidence_input`: the existing confidence factor document consumed by the finalizer.

`prepare` computes a stable `RUN-<20 HEX>` ID from the question, inputs, and canonical hashes of evidence, rules, and calculations. It exclusively creates `workspace/runs/<run_id>/` and writes:

- `review-request.json`
- `track-a-bundle.json`
- `confidence-input.json`
- `TRACK_A_INSTRUCTIONS.md`
- `TRACK_B_INSTRUCTIONS.md`
- `prepare-status.json`

The command prints canonical JSON containing the run ID, run directory, and required next files.

### Finalize

```powershell
ansim-review review-run finalize `
  --workspace F:\ansim-workspace `
  --run-id RUN-XXXXXXXXXXXXXXXXXXXX `
  --track-a-output F:\ansim-case\track-a-output.json `
  --track-b-output F:\ansim-case\track-b-output.json `
  --publish
```

`finalize` validates the run ID and existing prepared directory, exclusively copies Track A and Track B outputs into the run directory, hashes the four finalizer artifacts into `run-manifest.json`, calls `finalize_run`, resolves citations from the evidence SQLite database, and writes `review.html`.

With `--publish`, it exclusively copies the run-specific packet to `workspace/runs/final-review-packet.json`. Publication refuses to replace an existing packet, even if another run has already been finalized.

## Components

### `ansim_review.review_run`

Owns request validation, run ID calculation, exclusive artifact writes, manifest creation, finalization, reviewer HTML rendering, and publication. It does not execute retrieval, calculations, rules, or LLM tracks.

### `ansim_review.cli`

Adds nested `review-run prepare` and `review-run finalize` parsers and maps operational errors to stable exit codes:

- `0`: completed requested stage.
- `1`: output or publication target already exists.
- `2`: invalid request, missing artifact, hash/contract failure, or SQLite/rendering failure.

### Workflow documentation

`docs/CODEX_WORKFLOW.md` and `docs/CHATGPT_WEB_WORKFLOW.md` document the staged handoff and state that generated Track outputs must be saved as JSON files before finalization.

## Data Flow

1. Upstream deterministic tools produce evidence excerpts, calculation results, rule results, and confidence factors.
2. `prepare` validates those documents and creates an immutable Track A bundle.
3. Track A explains only from the bundle.
4. Track B independently audits every Track A claim.
5. `finalize` binds both outputs to their exact SHA-256 values in `run-manifest.json`.
6. Existing finalizer validates Track A, Track B, confidence, and abstention gates.
7. Reviewer HTML resolves visible citation content from SQLite.
8. Explicit publication selects the single packet consumed by the release builder.

## Error Handling

- Unknown fields, wrong format/version, invalid citations, invalid calculation/rule documents, malformed confidence input, and duplicate citation IDs fail before a run directory is created.
- If run creation succeeds, subsequent prepare artifacts are written with exclusive creation semantics.
- Finalize refuses missing prepared artifacts, existing Track outputs, existing manifests, existing final packets, or mismatched run IDs.
- A failed finalizer never publishes a packet.
- Reviewer HTML is written only after final packet creation and citation resolution succeed.

## Testing

Integration tests cover:

- deterministic preparation and byte-identical artifacts across two workspaces;
- refusal to overwrite an existing run;
- successful finalization with valid Track A and Track B fixture outputs;
- generation of run manifest, final packet, reviewer HTML, and published root packet;
- refusal to publish over an existing root packet;
- CLI exit codes for success, overwrite, and validation failure;
- `human_decision` remaining `null` in every machine packet.

## Non-Goals

- Invoking ChatGPT, Codex, or any external model.
- Generating Track A or Track B prose inside Python.
- Replacing retrieval, Math Engine, or Rule Engine commands.
- Automatically choosing which finalized run is a release candidate without an explicit `--publish` action.
