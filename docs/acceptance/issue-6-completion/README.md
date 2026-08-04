# Issue #6 remaining scope acceptance

## Current status

`IMPLEMENTED / EXECUTION_EVIDENCE_PENDING`

The post-M2 implementation is present on branch
`codex/issue-6-complete-drawing-pipeline` and PR #58:

- confirmed calibration is hash-bound and Math Engine-backed;
- staged extraction is quality-gated and produces only unconfirmed candidates;
- Review Packet v2 drawing evidence is validated and rendered as a self-contained HTML overlay.

## Required final verification

The following must be executed against the exact PR head from a complete repository checkout:

- focused calibration, extractor, and drawing renderer tests;
- full pytest, Ruff, strict mypy, and compileall;
- Python 3.11/3.13 wheel and package-resource smoke;
- one vector-PDF candidate fixture, one 600dpi raster candidate fixture, and one quality-rejected fixture;
- browser review of candidate confirmation, calibration handoff, and final packet rendering.

GitHub Actions run `30929218507` cannot serve as execution evidence because its four jobs returned `steps: null`. No Issue #6 closure is asserted by this file.


## Manual verification runner

GitHub Actions are not part of this verification path. Run the following from a clean Windows checkout after installing the project development extra:

    Set-Location F:\evidence-review-system
    git fetch origin codex/issue-6-complete-drawing-pipeline
    $prHead = (git ls-remote origin refs/heads/codex/issue-6-complete-drawing-pipeline | ForEach-Object { ($_ -split "\s+")[0] })
    git checkout --detach $prHead
    .\scripts\verify_issue_6_manual.ps1 -ExpectedCommit $prHead -Python311 C:\Python311\python.exe -Python313 C:\Python313\python.exe -VectorPdf F:\fixtures\vector-candidate.pdf -Raster600Dpi F:\fixtures\raster-600dpi.png -RejectedQualityFixture F:\fixtures\rejected-quality.json -BrowserEvidenceJson F:\fixtures\issue-6-browser-evidence.json

The script writes build\issue-6-manual-verification\report.json and exits non-zero unless every check is PASS. Missing interpreters, fixtures, or browser evidence are BLOCKED; they are never treated as a successful closure.

The browser evidence JSON must be created after a reviewer manually checks candidate confirmation, calibration handoff, and final Review Packet v2 rendering:

    {
      "candidate_confirmation": true,
      "calibration_handoff": true,
      "review_packet_rendering": true
    }

Fixture presence is hash-recorded but does not claim that a file is vector or 600dpi by filename alone. The reviewer must inspect those properties and retain the generated report with the fixture hashes. Issue #6 remains open until the report is PASS and the browser evidence is attached to the PR.
