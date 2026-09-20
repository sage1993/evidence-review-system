# ReviewMatter Architecture

## Purpose

This document defines the authority boundaries for the merged persistent ReviewMatter architecture on current `main`. The architecture is executable and was accepted through the migration program; dated migration acceptance records remain historical evidence rather than current runtime authority. Future commands or modules are current only after they exist at the exact checked-out HEAD and pass the applicable acceptance gates.

## Identity and authority

`ReviewMatter` is the mutable reviewer-work domain and `matter_id` is its stable identity. Existing drawing artifacts retain their `CaseManifest` and `case_id` semantics. A Matter identity must never be substituted for a drawing `case_id` or a Review Packet v2 `case_id`.

The authority order is:

1. preserved source bytes and source hash;
2. finalized immutable evidence records and the exact closed-file `evidence.sqlite` identity;
3. ReviewMatter work state, including issues, source bindings, evidence selections and drafts;
4. an immutable FormalizationSnapshot for one exact Matter revision;
5. deterministic retrieval, Math Engine results and approved Rule Engine results;
6. independently validated Track A and Track B outputs;
7. the immutable final Review Packet and its protected read-only projection;
8. a separate append-only Human Decision bound to the exact packet hash.

Matter work is not evidence or final authority. Draft observations and findings are explicitly non-authoritative. Machine packets keep `human_decision` null, and `READY_FOR_HUMAN_REVIEW` means ready for inspection rather than accepted or legally approved.

## User-work modes

Evidence Navigation is non-authoritative exploration of finalized evidence. Searching, opening citations or comparing sources must not create a formal run, Track output, packet, compliance conclusion or Human Decision. A result promoted into Matter work is revalidated against the current finalized snapshot and exact evidence database SHA-256.

ReviewMatter is mutable work state stored separately from `evidence.sqlite`. Its mutations use optimistic concurrency. Matter events and their projection commit atomically, and stale writers fail closed without partial revision changes.

Formalization is the only promotion boundary from Matter work to Formal Review. It requires the exact `matter_id` and expected revision, rejects required stale or unresolved issues, binds the exact finalized evidence snapshot and exact database SHA-256, and includes only explicitly promoted evidence or confirmed inputs. The existing Formal Review core remains authoritative and does not mutate Matter history.

## Evidence and source binding

Published evidence follows the finalized lifecycle:

```text
ingest → deterministic materialization → logical snapshot and retrieval verification
→ writer close → create-only publish → exact closed-file SHA-256 → read-only review
```

Review readers reject unfinalized databases, stale retrieval indexes, logical snapshot mismatches, failed SQLite integrity checks and `-wal`, `-shm` or `-journal` sidecars. Matter records that depend on evidence retain document, revision, page, evidence, bbox, source-hash and finalized-snapshot identity. Matter storage never writes to the evidence database.

If a source hash changes, every known dependent issue is invalidated. Unknown or unmodelled impact is treated as affected and becomes stale; heuristics must not claim that work is unaffected. A stale required issue cannot be formalized.

## Formal Review entrypoints

`QuestionPlan` and `ReviewScope` are control inputs, not evidence. Current `main` supports both persistent ReviewMatter Formalization and the direct `review-question prepare-plan → prepare → Track A → Track B` Formal Review entrypoint. ReviewMatter `formalize` is the only promotion from mutable Matter work into Formal Review; the direct question path does not create or mutate Matter work.

Both paths converge on the same Formal Review authority: immutable prepared inputs, deterministic retrieval/math/rule artifacts, validated Track A and Track B, finalizer-owned machine status, protected Review Workspace, and a separate packet-bound append-only Human Decision.
