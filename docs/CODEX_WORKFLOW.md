# Codex Workflow

Use local evidence only. Retrieval, Math Engine, and approved Rule Engine results must already exist as deterministic artifacts in an `ansim/review-run-request` document. Project code never invokes a model or API and never replaces deterministic output with prose calculations.

## 1. Prepare an immutable run

```powershell
python -m ansim_review review-run prepare `
  --workspace F:\ansim-workspace `
  --request F:\ansim-case\review-request.json
```

The command prints the stable run ID and creates `F:\ansim-workspace\runs\<RUN-ID>`. Use only these prepared files when producing Track outputs:

- `track-a-bundle.json`
- `TRACK_A_INSTRUCTIONS.md`
- `TRACK_B_INSTRUCTIONS.md`
- `confidence-input.json`

Track A may explain supplied evidence, CalculationResult, and RuleResult artifacts. It may not calculate, alter a rule status, assign confidence, abstain, or select a human decision. Save its JSON as `track-a-output.json`.

Run Track B independently against every Track A claim. Track B may audit but may not rewrite Track A or set confidence, final status, or a human decision. Save its JSON as `track-b-output.json`.

## 2. Finalize and explicitly publish

```powershell
python -m ansim_review review-run finalize `
  --workspace F:\ansim-workspace `
  --run-id RUN-XXXXXXXXXXXXXXXXXXXX `
  --track-a-output F:\ansim-case\track-a-output.json `
  --track-b-output F:\ansim-case\track-b-output.json `
  --publish
```

Finalization verifies artifact hashes, Track A integrity, the independent Track B audit, confidence factors, and abstention gates. It then writes the run-specific `final-review-packet.json` and `review.html`. `--publish` copies the exact packet to `runs/final-review-packet.json` for the release builder; it does not approve the result or set `human_decision`.

```bash smoke
python -c "from ansim_review.packaging.codex_bundle import CODEX_ROUTING_SECTION; assert 'never decide' in CODEX_ROUTING_SECTION.lower()"
```

For an abstention case, preserve every reason code and hand the packet to a named human reviewer.
