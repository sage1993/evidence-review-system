# Issue #6 browser manual annotation acceptance

This directory records the Windows localhost browser QA run for PR #54.
The run started from remote HEAD
`ea14453e47554fa0e2d4a886845b292657c3a649` and validated the implementation
commit `e30f0b0e2d9728f8a9bf4e9dd9e25752bc762213` on
`agent/issue-6-browser-manual-annotation`.

## Reproduction

```powershell
python scripts/run_drawing_annotation_workspace.py `
  --case-dir .\build\manual-qa\cases\CASE-001 `
  --source .\build\manual-qa\site-plan.png `
  --width 1400 `
  --height 1000 `
  --coordinate-system IMAGE_TOP_LEFT_PIXELS `
  --candidate-fixture .\build\manual-qa\candidates.json
```

The fixture source SHA-256 was
`2fd36280d5a6c32e6e61b7c24490acf7da4a93c6eedf904be5c3f2288ef8976d`.
The server printed a run-scoped URL bound to `127.0.0.1`.

## Manual observations

- Candidate list and SVG overlay stayed synchronized when selecting `CAND-BBOX` and `CAND-LINE`.
- The default action state had no selected radio button.
- 100%, 200%, and fit-to-page views were captured; the overlay remained inside the page canvas.
- POINT, BBOX, LINESTRING, and POLYGON capture controls reached their ready states.
- ACCEPTED, REJECTED, EDITED, and CREATED actions produced append-only confirmations.
- A Unicode reviewer identity was accepted and the confirmation filename used a server-derived `REV-` token.
- Unauthorized Origin and oversized/malformed JSON requests were rejected without filesystem-path disclosure.

Confirmation artifacts:

- ACCEPTED: `CONF-381E755475C37B8768D07FC8`
- REJECTED: `CONF-68E99BF09D7096B16D59C0E4`
- EDITED: `CONF-5355CF11C672BA77A91082F0`
- CREATED point: `CONF-EF46DF283D983602C33AA54E`
- CREATED polygon: `CONF-327C9334687B60C3942AED4B`

Screenshots:

- [100-percent.png](./100-percent.png)
- [200-percent.png](./200-percent.png)
- [fit-to-page.png](./fit-to-page.png)
- [polygon-created.png](./polygon-created.png)

## Automated results

See [cross-platform-validation.json](./cross-platform-validation.json) for the
current Python 3.11 acceptance evidence and
[manual-qa-report.json](./manual-qa-report.json) for the browser observations.

Windows Python 3.11.15 validation passed: documentation integrity, 950 pytest
tests with 5 skips, Ruff, mypy, compileall, 59 focused drawing/workspace tests
with 1 skip, wheel build/install, package-resource and namespace smoke, and all
four CLI entrypoint help checks.

Ubuntu Python 3.11 validation was not executed. WSL distro enumeration returned
`E_ACCESSDENIED`, and the Docker Desktop Linux daemon was unavailable. This is
recorded as `UBUNTU_ENV_UNAVAILABLE`, not as a code PASS. The observed GitHub
Actions run (`30822953376`) had no executed steps (`steps=null`), so the report
remains `MANUAL_PASS / CROSS_PLATFORM_VALIDATION_INCOMPLETE`, the PR remains
Draft, and no Ready, merge, or Issue #6 closure action was performed.
