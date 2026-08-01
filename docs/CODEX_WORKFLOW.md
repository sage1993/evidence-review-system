# Codex Workflow

Use local evidence only. Retrieval, Math Engine, and approved Rule Engine results must already exist as deterministic artifacts in an `ansim/review-run-request` document. Project code never invokes a model or API and never replaces deterministic output with prose calculations.

Shared status, attachment, Review Packet v2, and next-action rules are governed by `docs/CONTRACT_GOVERNANCE.md`.

## 1. Prepare an immutable run

```powershell
python -m ansim_review review-run prepare `
  --workspace F:\ansim-workspace `
  --request F:\ansim-case\review-request.json
```

The command prints the stable run ID and creates `F:\ansim-workspace\runs\<RUN-ID>`. Every attachment used by the run must first be copied under `inputs/original/` and recorded with its original name, stored path, SHA-256, byte size, MIME, and user-confirmed role. External mutable paths are not runtime authority.

Use only these prepared files when producing Track outputs:

- `track-a-bundle.json`
- `TRACK_A_INSTRUCTIONS.md`
- `TRACK_B_INSTRUCTIONS.md`
- `confidence-input.json`

Track A may explain supplied evidence, CalculationResult, and RuleResult artifacts. It may not calculate, alter a rule status, assign confidence, abstain, confirm drawing candidates, or select a human decision. Save its JSON as `track-a-output.json`.

Run Track B independently against every Track A claim. Track B may audit but may not rewrite Track A or set confidence, final status, drawing confirmation, or a human decision. Save its JSON as `track-b-output.json`.

## 2. Follow `next-action.json`

Project code does not invoke Track A or Track B. When agent work is required, the workflow writes a deterministic `next-action.json` document.

A Track A action declares:

```json
{
  "format": "ansim/next-action",
  "version": 1,
  "workflow_state": "WAITING_TRACK_A",
  "action": "PRODUCE_TRACK_A",
  "input_bundle": "track-a-bundle.json",
  "instructions": "TRACK_A_INSTRUCTIONS.md",
  "expected_output": "track-a-output.json",
  "track_a_validated": false
}
```

After writing the expected output, execute the declared `resume_command`. The runtime validates schema, hashes, citations, and registered numeric values before it may emit a Track B action.

A Track B action is valid only when:

- `workflow_state` is `WAITING_TRACK_B`;
- `action` is `PRODUCE_TRACK_B`;
- `track_a_validated` is `true`;
- Track A output has already passed deterministic validation.

Do not manually advance workflow state or construct a Track B action before that gate passes.

## 3. Finalize and explicitly publish

```powershell
python -m ansim_review review-run finalize `
  --workspace F:\ansim-workspace `
  --run-id RUN-XXXXXXXXXXXXXXXXXXXX `
  --track-a-output F:\ansim-case\track-a-output.json `
  --track-b-output F:\ansim-case\track-b-output.json `
  --publish
```

Finalization verifies artifact hashes, Track A integrity, the independent Track B audit, confidence factors, and abstention gates. It then writes the run-specific `final-review-packet.json` and `review.html`. `--publish` copies the exact packet to `runs/final-review-packet.json` for the release builder; it does not approve the result or set `human_decision`.

Review Packet v1 remains frozen. A v2 consumer must use the deterministic v1-to-v2 adapter and must not invent resolved evidence, drawing evidence, confirmed inputs, exceptions, or conflicts absent from v1.

```bash smoke
python -c "from ansim_review.packaging.codex_bundle import CODEX_ROUTING_SECTION; assert 'never decide' in CODEX_ROUTING_SECTION.lower()"
```

For an abstention case, preserve every reason code and hand the packet to a named human reviewer.
