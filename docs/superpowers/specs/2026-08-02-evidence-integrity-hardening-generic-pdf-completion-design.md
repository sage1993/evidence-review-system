# Evidence Integrity, Release Assurance, and Generic PDF Completion Design

Date: 2026-08-02

Related issues: #19, #20, #22, #25, #26

## 1. Purpose

This design completes the remaining trust-boundary and generic-document work after PR #23. The work is divided into four ordered stages so that evidence identity is stabilized before validator, release, and end-to-end changes depend on it.

```text
Stage 1  #19 Evidence page integrity
Stage 2  #25 Numeric grammar + #26 offline boundary
Stage 3  #20 Named reviewer attestation
Stage 4  #22 Generic PDF pipeline completion and legacy isolation
```

The stages are ordered, but Stage 2 may use two independent pull requests because the numeric validator and offline policy do not share runtime state.

## 2. Confirmed decisions

### 2.1 Release approval model

Issue #20 will use an internal process attestation model, not a cryptographic signature model.

- The current `signature` field will be removed from new contracts.
- The replacement field will be a strict attestation enum, not arbitrary free text.
- The system will verify the reviewer identifier, timestamp, exact candidate hash, exact packet hash, required checklist results, and canonical document shape.
- The system will not claim to authenticate the human identity cryptographically.
- Public-key signing is outside this scope and may be introduced later as a separate feature.

### 2.2 Evidence page authority

`pages.id` will be the authoritative page identity.

- `elements`, `tables`, and `visuals` will reference only `page_id` for page identity.
- Their revision and page number will be resolved by joining `pages`.
- Retrieval projections may cache document, revision, and page metadata, but the projection must be built from page joins and must never trust duplicated ingest values.

### 2.3 Numeric claim grammar

Track A claim text will support canonical ASCII numeric forms only.

Supported examples:

```text
0
-12
1,234
12.50
9.375%
+3
```

Unsupported examples will fail explicitly rather than being normalized silently:

```text
1e3
1E-3
.5
1_000
½
１２３
malformed comma groups such as 12,34
```

A value such as `.5` must be emitted as `0.5` by a deterministic source-normalization or calculation step before it can be used in a claim.

### 2.4 Offline assurance terminology

The application provides an application-level offline guard, not an operating-system security sandbox.

Two assurance levels will be named explicitly:

- `APPLICATION_OFFLINE_GUARD`: static policy checks plus runtime prevention of non-loopback network use by the Python process.
- `OS_ISOLATED`: an operator-supplied deployment boundary such as firewall rules, `--network none`, or a network namespace.

The project may validate the first level. It may document the second level, but it must not claim `OS_ISOLATED` unless the deployment environment supplies and records that control.

## 3. Delivery structure

### Stage 1 — PR 1: Evidence schema v2 and migration (#19)

This is the foundation for all later citation and release assertions.

### Stage 2 — PR 2 and PR 3: Validator and runtime hardening (#25, #26)

These two PRs may be developed in parallel after Stage 1 is merged.

### Stage 3 — PR 4: Process attestation contract (#20)

This PR depends on the finalized offline-assurance vocabulary from #26.

### Stage 4 — PR 5 and PR 6: Generic pipeline completion (#22)

The epic is completed through a generic parser/state PR followed by a namespace, fixture, and end-to-end cleanup PR.

## 4. Stage 1 design — Evidence schema v2 (#19)

### 4.1 Current problem

The current schema stores `revision_id`, `page_id`, and `page_number` independently in `elements`. `tables` and `visuals` have no direct page foreign key. SQLite can therefore accept rows whose identifiers describe different pages.

### 4.2 Schema v2

A new `schema_meta` table records the evidence schema version.

```sql
CREATE TABLE schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) STRICT;
```

The latest version is recorded as:

```text
schema_version = 2
```

The page-bearing tables become:

```text
pages
  id
  revision_id
  page_number
  width
  height

elements
  id
  page_id
  element_type
  raw_json
  raw_text
  normalized_text
  raw_payload_hash
  bbox_json
  parser_order

tables
  id
  page_id
  bbox_json
  raw_json
  normalized_json

visuals
  id
  page_id
  kind
  relative_path
  sha256
  bbox_json
  duplicate_group
```

`revision_id` and `page_number` are removed from `elements`, `tables`, and `visuals`. A row cannot claim a page independently of the referenced `pages` record.

`retrieval_records` gains `page_id`. Its `document_id`, `revision_id`, `page_number`, page dimensions, and source hash are generated only by joining:

```text
evidence row
-> pages
-> revisions
-> documents
```

### 4.3 BBox validation

A shared `validate_bbox_within_page()` function validates every non-null bbox before insert.

Required conditions:

- all four values are finite numbers;
- left <= right and bottom <= top;
- left and bottom are not below zero beyond the declared coordinate tolerance;
- right <= page width and top <= page height within tolerance;
- the page exists and is the page referenced by `page_id`.

The same validator is used by normal ingest, migration, table ingest, visual ingest, and case/drawing adapters.

### 4.4 Versioned, copy-on-write migration

Opening an old database will not silently mutate it.

New behavior:

```text
read schema version
  -> v2: open normally
  -> v1: raise SchemaUpgradeRequired
  -> unknown/newer: raise UnsupportedSchemaVersion
```

A dedicated command performs migration:

```powershell
evidence-review evidence migrate \
  --source evidence-v1.sqlite \
  --output evidence-v2.sqlite
```

Migration procedure:

1. Open the source database read-only.
2. Infer schema v1 only when `schema_meta` is absent and the expected v1 tables and columns match exactly.
3. Create a temporary v2 database beside the requested output.
4. Copy documents, revisions, and pages.
5. For each element, resolve `(revision_id, page_number)` to one page and verify that the old `page_id` equals that page.
6. For each table and visual, resolve `(revision_id, page_number)` to one page.
7. Validate every bbox against the resolved page dimensions.
8. Rebuild retrieval records and FTS from joins.
9. Run `PRAGMA integrity_check` and `PRAGMA foreign_key_check`.
10. Compare canonical logical snapshot hashes before and after migration.
11. Write a migration report containing source hash, destination hash, row counts, schema versions, and validation results.
12. Atomically rename the temporary database to the output path.

The source database remains unchanged. Migration fails without creating the final output when any page mapping or bbox is invalid.

### 4.5 Stage 1 error model

New deterministic errors:

- `SCHEMA_UPGRADE_REQUIRED`
- `UNSUPPORTED_SCHEMA_VERSION`
- `PAGE_REFERENCE_MISMATCH`
- `PAGE_REFERENCE_NOT_FOUND`
- `BBOX_OUT_OF_PAGE`
- `MIGRATION_LOGICAL_HASH_MISMATCH`
- `MIGRATION_OUTPUT_EXISTS`

### 4.6 Stage 1 tests

Unit tests:

- element references a page from another revision;
- old `page_id` conflicts with old revision/page number;
- missing page for table or visual;
- bbox below zero, inverted, non-finite, or beyond page bounds;
- valid boundary bbox at exact page edges;
- v1, v2, unknown, and newer schema detection.

Integration tests:

- valid v1 fixture migrates to v2;
- source DB bytes are unchanged;
- logical snapshot hash is preserved;
- retrieval citations resolve from page joins;
- FTS results are equivalent before and after migration;
- migration rollback leaves no final database after a bad row;
- new generic source-batch ingest creates v2 directly.

## 5. Stage 2A design — Numeric grammar (#25)

### 5.1 Numeric scanner

The regex-only implementation will be replaced by a deterministic scanner in a dedicated module, for example:

```text
src/evidence_review/llm_layer/numeric_grammar.py
```

The scanner returns token spans and the exact original token text. It does not round, localize, or normalize.

### 5.2 Supported grammar

Conceptual grammar:

```text
sign        := "+" | "-"
integer     := digits | grouped_digits
fraction    := "." digits
percent     := "%"
number      := sign? integer fraction? percent?
```

Rules:

- grouped integers must use groups of exactly three digits after the first group;
- a decimal must have digits on both sides of the decimal point;
- only ASCII digits, comma, dot, sign, and percent are accepted;
- exponent notation is not accepted;
- underscore separators are not accepted;
- Unicode numeric characters are not accepted;
- token text must remain byte-for-byte equal to `numeric_tokens` supplied in the claim.

### 5.3 Unsupported numeric-like detection

After supported token spans are identified, the validator scans the remaining text for numeric meaning that was not consumed.

It rejects:

- remaining ASCII digits;
- Unicode characters for which `unicodedata.numeric()` succeeds;
- exponent patterns adjacent to digits;
- underscores between digits;
- a dot immediately followed by a digit without a leading integer;
- malformed comma-separated digit groups.

The error distinguishes the two cases:

- `NUMERIC_TOKEN_MISMATCH`: declared tokens differ from extracted supported tokens;
- `UNSUPPORTED_NUMERIC_SYNTAX`: claim contains numeric-looking text outside the supported grammar.

### 5.4 Source and calculation authority

A supported claim token remains valid only when the exact token appears in at least one cited evidence excerpt or a referenced successful `CalculationResult`.

Unsupported source notation is not silently normalized inside Track A. A deterministic parser or calculation step must create a canonical representation before Track A may use it.

### 5.5 Stage 2A tests

Reject:

- `1e3` and `1E-3`;
- `.5`;
- `1_000`;
- `½`, superscript numerals, circled numerals, and full-width digits;
- `12,34` and `1,23,456`;
- a claim that declares an empty token list while containing numeric meaning.

Accept:

- integer, signed integer, decimal, percent, and valid thousands groups;
- Korean unit text adjacent to an accepted token;
- exact tokens sourced from evidence;
- exact tokens sourced from a successful calculation;
- nonnumeric identifiers when no numeric semantic pattern is present.

## 6. Stage 2B design — Offline boundary (#26)

### 6.1 One shared policy module

Runtime guard and release validator will import one policy definition.

The policy contains:

- forbidden network-client modules;
- forbidden process-spawning modules and APIs for release runtime code;
- allowed loopback address rules;
- prohibited non-loopback socket operations;
- a stable policy version and assurance-level enum.

The runtime and release scanner must not maintain separate block lists.

### 6.2 Static policy

The release source scanner checks the canonical runtime package and reports deterministic findings for:

- forbidden imports such as network clients;
- `subprocess`, `os.system`, and async subprocess APIs outside an explicit build-tool allowlist;
- dynamic import calls targeting blocked modules when the target is a string literal;
- scanner parse failures.

Build and development tools may be outside the packaged runtime boundary. The scanner operates on the exact file set included in the release manifest.

### 6.3 Runtime guard

The Python runtime guard will:

- block non-loopback `socket.create_connection`;
- block non-loopback `socket.socket.connect` and `connect_ex`;
- block non-loopback UDP `sendto`;
- allow IPv4 and IPv6 loopback;
- allow local Unix-domain sockets where supported;
- leave server-side `bind`, `listen`, `accept`, `send`, and `sendall` available so the localhost review UI continues to work;
- install before command dispatch and remain idempotent.

The guard is application protection, not protection against native code, a hostile interpreter, a preconnected descriptor, or an external process launched before the guard.

### 6.4 Deployment documentation

The operations guide will separate:

```text
Profile A: APPLICATION_OFFLINE_GUARD
Profile B: OS_ISOLATED
```

Profile B examples:

- Windows outbound firewall rule for the executable;
- container execution with `--network none`;
- Linux network namespace or equivalent host control.

A release report records only the verified profile. It may not label an ordinary application-guard run as OS-isolated.

### 6.5 Manifest path containment

The release validator will resolve every manifest entry and verify it remains below the manifest root before reading it. This closes the existing `../` validation gap while modifying the same trust boundary.

### 6.6 Stage 2B tests

- runtime and release validator reference the same policy version;
- all forbidden imports produce the same finding format;
- non-loopback IPv4 and IPv6 TCP are blocked;
- non-loopback UDP is blocked;
- loopback browser server remains usable;
- SQLite and local file operations remain usable;
- prohibited subprocess imports and literal invocations are detected;
- manifest `../` and absolute paths are rejected before file access;
- documentation and release report use the exact assurance-level names.

## 7. Stage 3 design — Named reviewer attestation (#20)

### 7.1 New contract

New releases use:

```json
{
  "format": "evidence-review/human-attestation",
  "version": 1,
  "assurance_level": "PROCESS_ATTESTATION",
  "reviewer_id": "reviewer@example.com",
  "reviewed_at": "2026-08-02T02:00:00+09:00",
  "attestation": "REVIEWED_AND_ACCEPTED_FOR_RELEASE",
  "release_candidate_hash": "...",
  "packet_hash": "...",
  "checks": []
}
```

`attestation` is a fixed enum. It is not a signature string and does not contain an email/password-like convention.

### 7.2 Validation guarantees

The validator guarantees only that:

- the document is canonical and has no unknown fields;
- a nonempty reviewer identifier is present;
- the timestamp is timezone-aware ISO-8601;
- the fixed attestation statement is present;
- candidate and packet hashes match the current release inputs;
- every required checklist item appears once, is `PASS`, and references nonempty evidence;
- the acceptance file is not overwritten by the writer.

The validator does not guarantee that the named reviewer actually created the file.

### 7.3 Release status semantics

`RELEASE_READY` means:

```text
automated release checks passed
AND
one structurally valid named-reviewer process attestation matches the release hashes
```

Release output also includes:

```text
attestation_assurance = PROCESS_ATTESTATION
cryptographic_identity_verified = false
```

A missing, malformed, stale, or mismatched attestation leaves the release `BLOCKED`.

### 7.4 Legacy policy

`ansim/human-acceptance` remains readable only by an explicit legacy inspection adapter.

- It cannot authorize a new `evidence-review` release.
- The migration tool may produce a draft new attestation with copied reviewer/check metadata, but a reviewer must explicitly issue the new record.
- New documentation, fixtures, and release outputs do not use `signature` terminology.

### 7.5 Stage 3 tests

- unknown fields and old format are rejected for a new release;
- altered candidate hash or packet hash blocks release;
- duplicate, missing, pending, or failed checklist items block release;
- missing timezone blocks release;
- invalid attestation enum blocks release;
- append-only writer refuses overwrite;
- release report states `PROCESS_ATTESTATION` and `cryptographic_identity_verified=false`;
- legacy record can be inspected but cannot set `RELEASE_READY`.

## 8. Stage 4 design — Generic PDF pipeline completion (#22)

### 8.1 Remaining scope after PR #23

PR #23 delivered source-batch v1, hash-based IDs, ODL ingestion, generic CLI naming, and legacy-path separation. The epic remains open because the implementation still has:

- one hard-coded parser kind in the source-batch contract;
- only two preparation states;
- generic release code that still emits legacy `ansim` names in several paths and formats;
- an internal package namespace named `ansim_review`;
- legacy-named golden fixtures and release tests in normal paths;
- no complete fixture matrix for report, table, scan, and drawing inputs;
- no static gate proving that new artifacts are free of sample identifiers.

### 8.2 Source-batch v2 and parser registry

Source-batch v2 changes parser binding to:

```json
{
  "kind": "OPENDATALOADER_JSON",
  "adapter_version": "1.0.0",
  "artifact_path": "inputs/parser/result.json"
}
```

`kind` is a validated stable identifier rather than a Python `Literal` closed to one value. Runtime support is decided by a parser adapter registry.

Adapter interface:

```text
adapter ID
adapter version
supported source roles
artifact validation
parse(source, binding) -> canonical parsed document
```

Initial registered adapter:

- `OPENDATALOADER_JSON@1.0.0`

Future adapters can be registered without revising the source-batch schema. Unknown adapters produce `UNSUPPORTED_PARSER`, not a generic schema exception.

Source-batch v1 remains readable through a legacy decoder and maps to the initial ODL adapter version. New manifests are written as v2.

### 8.3 Generic input state model

The source preparation model becomes a strict transition system:

```text
RECEIVED
-> CLASSIFYING_INPUTS
-> PENDING_PARSER_OUTPUT
-> PENDING_REFERENCE_INGESTION
-> PENDING_DRAWING_INGESTION
-> INPUT_CONFIRMATION_REQUIRED
-> READY_TO_EVALUATE
```

Terminal or exceptional states:

```text
BLOCKED
FAILED
UNSUPPORTED_PARSER
SOURCE_CONFLICT
```

Role routing:

- `REFERENCE_DOCUMENT` enters evidence DB ingestion.
- `CASE_DRAWING` enters case/drawing evidence processing and never enters the shared reference DB.
- `CASE_TABLE` enters a case-scoped structured table adapter.
- `SUPPORTING_IMAGE` remains supporting evidence and cannot directly bind deterministic rule inputs.

Every transition is represented by a canonical state document with reason codes and resumability.

### 8.4 Canonical namespace migration

The canonical Python package moves from:

```text
ansim_review
```

to:

```text
evidence_review
```

Migration procedure:

1. Move canonical modules and package data to `src/evidence_review`.
2. Update imports, mypy package config, test imports, console entry point, package-data paths, and build scripts.
3. Move legacy artifact readers under `evidence_review.legacy`.
4. Retain `ansim-review` only as a deprecated console alias that dispatches to a legacy compatibility command and prints a deprecation notice.
5. Do not retain `ansim_review` as the canonical implementation namespace.
6. Add a repository scan test that allows `ansim` only in explicit legacy adapters, migration fixtures, compatibility tests, and historical design records.

This migration is isolated in its own PR so import failures are easy to identify and revert.

### 8.5 Generic release names

The release validator and builder use configurable product metadata and emit:

```text
evidence-review/release-validation
evidence.sqlite
evidence-review-runtime-<version>.zip
```

Legacy filenames are accepted only by legacy inspection or migration commands.

### 8.6 Fixture matrix

All fixtures are synthetic or redistribution-safe. At minimum:

1. text-heavy policy/guideline PDF;
2. ordinary report PDF with headings and paragraphs;
3. table-heavy PDF;
4. image-only scanned PDF with declared parser output;
5. architectural drawing PDF routed as `CASE_DRAWING`;
6. same filename with different bytes;
7. different filenames with identical bytes;
8. unsupported parser adapter;
9. missing parser output;
10. malformed parser/source binding.

The sample housing guideline remains only as an optional legacy fixture and is not needed for generic acceptance.

### 8.7 Generic end-to-end acceptance

End-to-end scenarios:

#### Scenario A — Text reference

```text
source-batch v2
-> ODL adapter
-> schema v2 evidence DB
-> retrieval
-> review packet
```

#### Scenario B — Mixed reference batch

A guideline, report, and table-heavy PDF are ingested in one batch without filename inference.

#### Scenario C — Scan pending parser

An image-only scan without parser output stops at `PENDING_PARSER_OUTPUT` and creates no empty evidence database.

#### Scenario D — Drawing route

A drawing source is routed to `PENDING_DRAWING_INGESTION` and is not inserted into the shared reference database.

#### Scenario E — Legacy inspection

A legacy `ansim/*` artifact can be inspected or migrated, but no new run or release writes an `ansim/*` format.

### 8.8 Stage 4 tests

- source-batch v1 read compatibility and v2 write behavior;
- adapter registry lookup and unsupported-adapter state;
- role-based routing and forbidden cross-lane ingestion;
- all state transitions and invalid transitions;
- package import and CLI tests after namespace migration;
- repository scan for forbidden new `ansim` identifiers;
- generic release filenames and JSON formats;
- the complete fixture matrix;
- byte reproducibility for the same inputs, adapter versions, schema version, rule manifest, and formula manifest.

## 9. Cross-stage invariants

The following invariants apply to every PR:

1. User filenames and titles are display metadata, not identity.
2. All IDs and hashes are deterministic and canonical.
3. Existing immutable source files and old databases are never modified in place.
4. Any migration is copy-on-write and produces a machine-readable report.
5. Unknown fields and unsupported versions fail closed.
6. No LLM output can create numeric authority, page identity, release authority, or parser authority.
7. New artifacts use `evidence-review/*` formats.
8. Legacy behavior is isolated and explicitly named.
9. Each PR starts with failing regression tests and ends with full CI.
10. A stage is not merged while its required migration, compatibility, or rollback test is missing.

## 10. Pull request dependency and merge gates

```text
PR 1  #19 schema v2
  |
  +--> PR 2  #25 numeric grammar
  |
  +--> PR 3  #26 offline policy
            |
            +--> PR 4  #20 attestation
                     |
                     +--> PR 5  #22 parser registry + state model
                              |
                              +--> PR 6  #22 namespace + fixtures + E2E
```

PR 2 and PR 3 may proceed in parallel after PR 1. All later PRs rebase on the previous merged stage.

Every PR merge gate requires:

- targeted unit and integration tests;
- full `pytest -v`;
- Ruff;
- strict mypy;
- compileall;
- deterministic golden/byte-equivalence checks where relevant;
- no unresolved critical or important review findings.

## 11. Rollback strategy

- Schema migration never overwrites the source database, so rollback means continuing to use the v1 source while the migration defect is fixed.
- Validator changes are isolated and can be reverted without changing stored evidence.
- Attestation v1 is introduced as a new format; legacy inspection remains available, so rollback does not corrupt old records.
- Namespace migration is isolated in PR 6 and must retain one deprecated console alias, making rollback limited to package/import changes.
- Stage 4 state and manifest versions are explicit; old readers reject newer versions rather than interpreting them incorrectly.

## 12. Completion criteria

### Issue #19

All page-bearing evidence derives revision, page number, dimensions, and bbox validity from one verified `pages` row. A v1 database can be migrated copy-on-write with equivalent logical retrieval output.

### Issue #25

Every numeric meaning in Track A claim text is either an exact supported token backed by cited evidence or a successful calculation, or the claim fails with an explicit unsupported-syntax error.

### Issue #26

Runtime, release validation, reports, and documentation share one policy and use assurance language that matches the actual application-level and operator-level controls.

### Issue #20

A new release can be authorized only by a matching named-reviewer process attestation, and no field or document claims cryptographic identity verification.

### Issue #22

Arbitrary supported PDFs are routed and processed without sample filename assumptions; new manifests, runs, databases, release artifacts, package namespace, and user documentation use `evidence-review`; legacy `ansim` handling exists only in explicitly isolated compatibility code and fixtures.