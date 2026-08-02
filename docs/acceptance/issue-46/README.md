# Issue #46 LAW3 lineage acceptance record

This directory preserves the non-example lineage manifest and migration report used for the Issue #46 acceptance run.

## Mapping

- Legacy document: `LAW3`
- Canonical document: `DOC-ACFD68E34043268C`
- Source PDF SHA-256: `acfd68e34043268c8f76d9a14349cee80199c058accbfc6c0e67a060e7d8b328`
- Reviewer: `user-confirmed-via-codex`
- Reviewed at: `2026-08-02T18:20:18+09:00`

## Acceptance result

- CLI status: `MIGRATED`
- Source DB SHA-256 before/after: `09cbba29f89568458236158c14cbf10f49113584ce90f9fe6fc6816336bd5500`
- Output integrity: `ok`
- Foreign-key violations: `0`
- Unresolved lineage: `[]`
- Legacy rows remaining: `0`
- Canonical document and revision preserved: yes
- Related lineage tests: `43 passed`

## Reproduction

The binary databases remain under the ignored `build/` directory. Recreate the derived lineage source from the LAW3 evidence database, then run:

```powershell
.\\.venv\\Scripts\\python.exe scripts\\prepare_law3_lineage_source.py `
  --source build\\LAW3\\evidence.sqlite `
  --output build\\LAW3\\lineage-source\\evidence.sqlite `
  --manifest manifests\\law3-legacy-lineage.json

.\\.venv\\Scripts\\python.exe -m evidence_review evidence migrate-lineage `
  --source build\\LAW3\\lineage-source\\evidence.sqlite `
  --manifest manifests\\law3-legacy-lineage.json `
  --output build\\LAW3\\migrated\\evidence.sqlite
```

The complete reviewed inputs and output verification are preserved in the two JSON files in this directory.
