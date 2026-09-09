# ChatGPT Web Workflow

Build or upload the reproducible offline ZIP. The runtime performs no API calls and requires no package installation. Source PDFs are excluded by default; evidence records retain source hashes and coordinates.

## Source registration

Before beginning Track work, register each user-provided PDF through an `evidence-review/source-batch` manifest and create `evidence/evidence.sqlite` locally. Do not infer document roles from filenames or titles.

If a PDF has no parser artifact, keep it in `PENDING_PARSER_OUTPUT`. Do not ask ChatGPT to invent extracted text, tables, coordinates, or page references.

## Prepared inputs

First run `review-run prepare` in the local workspace. Upload or provide only the generated run files needed for the selected track.

For Track A, provide:

- `TRACK_A_INSTRUCTIONS.md`
- `track-a-bundle.json`

Return one JSON object that follows the Track A contract and save it locally as `track-a-output.json`. Do not calculate, change deterministic results, assign confidence, abstain, or set a human decision.

For Track B, begin an independent audit using:

- `TRACK_B_INSTRUCTIONS.md`
- `track-a-bundle.json`
- `track-a-output.json`

Audit every Track A claim exactly once and save the returned JSON as `track-b-output.json`. Track B must not rewrite Track A or set the final status.

## Local finalization

Pass both files back to the offline runtime:

```powershell
evidence-review review-run finalize `
  --workspace F:\evidence-review-workspace `
  --run-id RUN-XXXXXXXXXXXXXXXXXXXX `
  --track-a-output F:\review-case\track-a-output.json `
  --track-b-output F:\review-case\track-b-output.json `
  --publish
```

The local deterministic finalizer validates both untrusted outputs. A ChatGPT response is not accepted merely because it is well-formed; citation, calculation, rule, confidence, and Track B integrity checks must all pass. `--publish` keeps compatibility by reporting the run-local packet; it does not create a workspace-global packet copy.

```bash smoke
python -c "from evidence_review.packaging.project_instructions import render_project_instructions; assert 'human_decision' in render_project_instructions()"
```

A ready case and an abstention case use the same deterministic sequence. The final machine packet never contains a selected human decision.
