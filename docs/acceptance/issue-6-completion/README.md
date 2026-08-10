# Issue #6 remaining scope acceptance

## Current status

`MANUAL_PASS / ACTIONS_BILLING_BLOCKED`

The post-M2 implementation is present on branch
`codex/issue-6-complete-drawing-pipeline` and PR #58:

- confirmed calibration is hash-bound and Math Engine-backed;
- staged extraction is quality-gated and produces only unconfirmed candidates;
- Review Packet v2 drawing evidence is validated and rendered as a self-contained HTML overlay.

Issue #6 was manually verified at exact HEAD
`f91cbfd06a77ce0e7e73bd7008d91a1f6e8c6e88` on Windows. The review packet and
separate human decision record are retained under the sample-PDF verification
workspace. The machine packet keeps `human_decision: null`; the reviewer record
is `SATISFIED` and is bound to Packet SHA-256
`170aeaf7f8d3d29d024f6f4a9c5f164e8bf4cfb1f6d7e90d9502708ccb638117`.

## Required final verification

The following must be executed against the exact PR head from a complete repository checkout:

- focused calibration, extractor, and drawing renderer tests;
- full pytest, Ruff, strict mypy, and compileall;
- Python 3.11/3.13 wheel and package-resource smoke;
- one vector-PDF candidate fixture, one 600dpi raster candidate fixture, and one quality-rejected fixture;
- browser review of candidate confirmation, calibration handoff, and final packet rendering.

GitHub Actions is not used as the acceptance dependency. The observed account
billing/spending-limit block is recorded as `ACTIONS_BILLING_BLOCKED`; it is not
an Actions PASS and does not replace the manual evidence below.


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

Fixture presence is hash-recorded but does not claim that a file is vector or 600dpi by filename alone. The reviewer must inspect those properties and retain the generated report with the fixture hashes.

## Recorded manual results

- pytest: `1023 passed, 5 skipped`
- Ruff: PASS
- mypy: PASS (`171` source files)
- compileall: PASS
- Python 3.11 and 3.13 wheel/install and CLI help smoke: PASS
- documentation integrity: PASS, `errors=0`, `warnings=70`, SHA-256
  `97a0d9022648e07bfd3ff5a19df9d41889323b4a06b2137dd9ca6c9bf2e4a62d`
- browser evidence: annotation calibration handoff and Review Packet v2 visible;
  evidence SHA-256 `745392b0b07357659bf424270a6aa85c32c5c2110303c57fbd512bf776aee538`

Issue #6 closure is recorded against the manual gates above. Merging PR #58 into
`main` remains a separate maintainer action.
