# Korean Retrieval and Formal Review Invariants Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Korean natural-language formal-review questions retrieve relevant traceable evidence despite spacing/particle/numeric-format differences, and make zero-evidence/zero-claim, missing-input, snapshot-lineage, and Track A retry behavior fail closed and internally consistent.

**Architecture:** Keep the existing offline FTS5 pipeline and add a deterministic Korean query-variant layer with three bounded groups (entity, numeric, concept), then feed those groups into separate weighted retrieval channels so matching across groups raises rank without introducing unrestricted token-OR. Preserve exact citations for every returned/context hit. Downstream, derive confidence from evidence availability, prohibit vacuous Track B acceptance, carry snapshot/missing-input lineage through the legacy review packet compatibly, and make same-path Track A submission idempotent only after successful validation.

**Tech Stack:** Python 3.11/3.13, stdlib `re`/`unicodedata`, SQLite FTS5 (`unicode61`), existing `ansim_review` contracts/retrieval/finalizer/review-packet modules, pytest, Ruff, mypy. No new runtime dependency and no model/API query rewriting.

## Global Constraints

- Work directly on `main`; do not create a feature branch for this tranche.
- All user questions stay on the formal Track A → validation → Track B → final packet path; no quick-review mode.
- Keep the runtime offline; do not add network/model/API calls.
- Do not replace grouped retrieval with unrestricted token OR.
- Every returned evidence/context record must retain exact document/revision/page/evidence/bbox/source-hash citation identity.
- Preserve parser output and evidence source authority; retrieval may add derived query/context metadata only.
- Legacy review-packet readers remain backward compatible with packets that predate the new optional lineage fields.
- Track A create-only immutability remains authoritative; never overwrite a differing existing artifact.
- Windows is the primary acceptance platform. Final integration verification is required on Python 3.11 and 3.13 under #93.
- GitHub Actions status must be reported separately from manual Windows validation; never call local validation “Actions PASS”.

---

## File Structure

- Create `src/ansim_review/retrieval/korean_variants.py` — deterministic Korean particle stripping, subject/entity combination, numeric formatting variants, and bounded concept variants.
- Modify `src/ansim_review/retrieval/index.py` — expose a literal FTS helper for named grouped channels and a page-adjacent element loader for structural context.
- Modify `src/ansim_review/retrieval/fusion.py` — add explicit weights for `fts_entity`, `fts_numeric`, `fts_concept`, and `structural_context`.
- Modify `src/ansim_review/retrieval/bundle.py` — execute grouped channels, fuse seeds, add cited structural context, and export query-variant trace metadata.
- Modify `src/ansim_review/review_question.py` — derive confidence input from evidence availability instead of unconditional `1.0` and preserve existing snapshot input.
- Modify `src/ansim_review/llm_layer/track_b.py` — reject `ACCEPT` when Track A contains no auditable claims.
- Modify `src/ansim_review/contracts/review.py` — add backward-compatible optional `snapshot_sha256` and `missing_inputs` fields to the legacy `ReviewPacket` dataclass.
- Modify `src/ansim_review/contracts/codecs.py` — decode the two new fields when present and accept old packets where they are absent.
- Modify `src/ansim_review/abstention/finalizer.py` — derive snapshot/missing-input lineage from the manifest-bound Track A bundle and emit it in new final packets.
- Modify `src/ansim_review/review_packet/builder.py` — count packet-level missing inputs and expose snapshot lineage consistently in audit metadata.
- Modify `src/ansim_review/review_run.py` — accept a validated Track A file already located at the canonical target path without rewriting it; preserve create-only behavior for differing external files.
- Test `tests/unit/retrieval/test_korean_variants.py` — new deterministic variant contract.
- Modify/Test `tests/integration/retrieval/test_fts_lexical_channels.py` — grouped channel/fusion contract.
- Create `tests/integration/retrieval/test_korean_formal_review_retrieval.py` — representative Korean question + facility/1,500㎡ regression and context assertions.
- Modify/Test `tests/unit/review_question/test_request_builder.py` — zero-evidence confidence regression.
- Modify/Test `tests/unit/llm_layer/test_track_b_validator.py` — empty-audit/vacuous-ACCEPT regression.
- Modify/Test `tests/integration/abstention/test_finalizer.py` — snapshot and Track A missing-input packet lineage.
- Modify/Test `tests/unit/review_packet/test_builder.py` — summary count/snapshot audit projection consistency.
- Modify/Test `tests/unit/review_question/test_track_a_submission.py` — same-path Track A idempotency and differing-artifact conflict.
- Modify/Test `tests/integration/review_question/test_review_question_cli.py` — end-to-end representative question contract where practical with deterministic fixtures.

---

### Task 1: Deterministic Korean grouped query variants

**Files:**
- Create: `src/ansim_review/retrieval/korean_variants.py`
- Create: `tests/unit/retrieval/test_korean_variants.py`

**Interfaces:**
- Consumes: normalized primary question text (`str`).
- Produces: `GroupedQueryVariants(entity: tuple[str, ...], numeric: tuple[str, ...], concept: tuple[str, ...])` and `derive_korean_query_variants(primary: str) -> GroupedQueryVariants`.
- Later tasks consume the exact group names `entity`, `numeric`, and `concept`; keep ordering deterministic and deduplicate within each tuple.

- [ ] **Step 1: Write the failing regression for the real question**

```python
from ansim_review.retrieval.korean_variants import derive_korean_query_variants


def test_real_question_derives_entity_numeric_and_concept_groups() -> None:
    variants = derive_korean_query_variants(
        "청소년 문화의집은 면적이 1500제곱미터 이상이어야 한다."
    )

    assert variants.entity == ("청소년 문화의집", "청소년문화의집")
    assert variants.numeric == (
        "1500",
        "1,500",
        "1500제곱미터",
        "1,500제곱미터",
    )
    assert variants.concept == ("면적", "연면적", "연건축면적", "이상")
```

Also add a determinism test that calls the function twice and asserts equality, plus a safety test that an unrelated short question such as `"기준을 확인한다."` does not fabricate numeric variants.

- [ ] **Step 2: Run the new unit test and verify RED**

Run:

```powershell
python -m pytest -v tests/unit/retrieval/test_korean_variants.py
```

Expected: collection/import failure because `korean_variants.py` does not exist.

- [ ] **Step 3: Implement the minimal deterministic parser**

Create these exact public types/functions:

```python
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GroupedQueryVariants:
    entity: tuple[str, ...]
    numeric: tuple[str, ...]
    concept: tuple[str, ...]


def derive_korean_query_variants(primary: str) -> GroupedQueryVariants:
    ...
```

Implementation rules:

1. Normalize with the existing `normalize_text()` behavior before token analysis.
2. Strip terminal punctuation from whitespace tokens.
3. Strip only this bounded particle/sentence suffix set from Hangul tokens when the remaining stem is at least two characters: `은`, `는`, `이`, `가`, `을`, `를`, `에`, `에서`, `으로`, `로`, `와`, `과`, `도`, `이어야`, `여야`, `한다`.
4. Detect the first measurement/constraint token (`면적` family, a numeric token, or `이상`/`이하`) and treat the preceding non-empty stripped tokens as the subject/entity phrase. Emit both spaced and whitespace-free entity forms when they differ.
5. Parse a numeric token with `(?P<number>\d[\d,]*)(?P<unit>제곱미터|㎡)?`; emit comma-free and three-digit-grouped forms, then the same forms with the detected unit when a unit exists.
6. Use a bounded approved concept map:

```python
_CONCEPT_VARIANTS = {
    "면적": ("면적", "연면적", "연건축면적"),
    "연면적": ("면적", "연면적", "연건축면적"),
    "연건축면적": ("면적", "연면적", "연건축면적"),
    "이상": ("이상",),
    "이하": ("이하",),
}
```

7. Never emit arbitrary OR tokens from the full sentence; only these three groups are produced.
8. Preserve first-occurrence ordering using an ordered-dedup helper rather than a set iteration.

- [ ] **Step 4: Run unit tests and verify GREEN**

```powershell
python -m pytest -v tests/unit/retrieval/test_korean_variants.py tests/unit/retrieval/test_query_normalization.py
```

Expected: PASS; existing query normalization behavior remains unchanged.

- [ ] **Step 5: Commit**

```powershell
git add src/ansim_review/retrieval/korean_variants.py tests/unit/retrieval/test_korean_variants.py
git commit -m "feat: derive deterministic Korean query variants (#95)"
```

---

### Task 2: Add grouped FTS channels and multi-group fusion

**Files:**
- Modify: `src/ansim_review/retrieval/index.py`
- Modify: `src/ansim_review/retrieval/fusion.py`
- Modify: `src/ansim_review/retrieval/bundle.py`
- Modify: `tests/integration/retrieval/test_fts_lexical_channels.py`

**Interfaces:**
- Consumes: `derive_korean_query_variants(primary)` from Task 1.
- Produces: `search_fts_literal(connection, query, *, channel, limit=20) -> tuple[RetrievalHit, ...]` supporting only `fts_entity`, `fts_numeric`, `fts_concept`; bundle query metadata gains `derived_variants` with the three ordered arrays.
- Existing `fts_phrase` and `fts_token_and` behavior stays intact.

- [ ] **Step 1: Add failing channel and fusion tests**

Extend `test_fts_lexical_channels.py` with evidence records such as:

```python
facility = "청소년문화의집은 다양한 유형의 청소년수련시설 중 가장 작은 규모의 시설"
criterion = "청소년수련관은 연건축면적이 1,500제곱미터 이상이어야 한다"
```

Add assertions that `build_evidence_bundle()` for the representative question:

```python
bundle = build_evidence_bundle(
    store.require_connection(),
    {
        "question": "청소년 문화의집은 면적이 1500제곱미터 이상이어야 한다.",
        "synonym_manifest": {},
        "expansions": [],
        "limit": 20,
    },
)

assert {hit["evidence_id"] for hit in bundle["hits"]} >= {
    "E-CULTURE-HOUSE",
    "E-YOUTH-CENTER-1500",
}
assert bundle["query"]["derived_variants"] == {
    "entity": ["청소년 문화의집", "청소년문화의집"],
    "numeric": ["1500", "1,500", "1500제곱미터", "1,500제곱미터"],
    "concept": ["면적", "연면적", "연건축면적", "이상"],
}
```

Assert at least one culture-house hit contains an `fts_entity` score and the 1,500㎡ criterion contains `fts_numeric` plus `fts_concept`. Add an assertion that no emitted score uses a generic `fts_token_or` channel.

- [ ] **Step 2: Run the focused integration test and verify RED**

```powershell
python -m pytest -v tests/integration/retrieval/test_fts_lexical_channels.py
```

Expected: representative Korean test fails with no relevant hits / missing `derived_variants`.

- [ ] **Step 3: Expose a bounded literal-channel helper in `index.py`**

Add:

```python
_GROUP_CHANNELS = frozenset({"fts_entity", "fts_numeric", "fts_concept"})


def search_fts_literal(
    connection: sqlite3.Connection,
    query: str,
    *,
    channel: str,
    limit: int = 20,
) -> tuple[RetrievalHit, ...]:
    if channel not in _GROUP_CHANNELS:
        raise ValueError(f"unsupported grouped FTS channel: {channel}")
    return _search_fts(
        connection,
        query,
        match_expression=_phrase_match_expression(query),
        channel=channel,
        limit=limit,
    )
```

Do not expose arbitrary raw FTS expressions.

- [ ] **Step 4: Add explicit fusion weights**

Extend `CHANNEL_WEIGHTS` with:

```python
"fts_entity": Decimal("0.40"),
"fts_numeric": Decimal("0.20"),
"fts_concept": Decimal("0.10"),
```

These weights accumulate only when the same evidence is matched by different groups; multiple variants within one group continue to collapse into one channel score via `RetrievalHit.with_channel()`.

- [ ] **Step 5: Wire grouped variants into `build_evidence_bundle()`**

Add a helper with the exact shape:

```python
def _derived_variant_hits(
    connection: sqlite3.Connection,
    primary: str,
    limit: int,
) -> tuple[tuple[RetrievalHit, ...], ...]:
    ...
```

For each derived entity/numeric/concept term, call `search_fts_literal()` with the corresponding channel and rewrite `ChannelScore.detail` to `derived:<group>:<term>`. Append these channels after the existing origin channels and before fusion.

Add to the returned query document:

```python
"derived_variants": {
    "entity": list(variants.entity),
    "numeric": list(variants.numeric),
    "concept": list(variants.concept),
},
```

- [ ] **Step 6: Run retrieval regression suites**

```powershell
python -m pytest -v `
  tests/unit/retrieval/test_korean_variants.py `
  tests/unit/retrieval/test_query_normalization.py `
  tests/integration/retrieval/test_fts_lexical_channels.py `
  tests/integration/retrieval/test_fts_retrieval.py `
  tests/integration/retrieval/test_hybrid_fusion.py
```

Expected: PASS with existing exact-phrase/token-AND ordering tests unchanged.

- [ ] **Step 7: Commit**

```powershell
git add src/ansim_review/retrieval/index.py src/ansim_review/retrieval/fusion.py src/ansim_review/retrieval/bundle.py tests/integration/retrieval/test_fts_lexical_channels.py
git commit -m "feat: add grouped Korean retrieval channels (#95)"
```

---

### Task 3: Add cited structural context for adjacent parser elements

**Files:**
- Modify: `src/ansim_review/retrieval/index.py`
- Modify: `src/ansim_review/retrieval/fusion.py`
- Modify: `src/ansim_review/retrieval/bundle.py`
- Create: `tests/integration/retrieval/test_korean_formal_review_retrieval.py`

**Interfaces:**
- Consumes: fused seed `RetrievalHit` records from Task 2.
- Produces: `load_adjacent_element_hits(connection, seed, *, radius=1) -> tuple[RetrievalHit, ...]`; every context hit has its own evidence ID/bbox/source hash and channel `structural_context`.
- No context text is concatenated into the seed citation.

- [ ] **Step 1: Write the failing structural-context fixture**

Create a deterministic `EvidenceSnapshot` with one page containing parser-ordered elements:

```text
E-ROW-LABEL       parser_order=10  "청소년수련관"
E-ROW-CRITERION   parser_order=11  "연건축면적이 1,500제곱미터 이상이어야 하며 ..."
E-CULTURE-LABEL   parser_order=20  "청소년문화의집"
E-CULTURE-DESC    parser_order=21  "다양한 유형의 청소년수련시설 중 가장 작은 규모의 시설 ..."
```

Run `build_fts_index()` then the representative question. Assert the exported hits include all four exact evidence IDs (seed or structural context), and for each returned hit `citation` is non-null and points to its own evidence ID.

Also assert structural context never crosses to another page/revision and never returns more than `radius` preceding + `radius` following element per seed.

- [ ] **Step 2: Run the new test and verify RED**

```powershell
python -m pytest -v tests/integration/retrieval/test_korean_formal_review_retrieval.py
```

Expected: seed matches may exist after Task 2, but adjacent row label/description assertions fail.

- [ ] **Step 3: Implement page-local adjacent element loading**

In `index.py`, use the seed evidence ID to resolve `elements.page_id` and `elements.parser_order`, then query only the same page and only element rows in `[order-radius, order+radius]`, excluding the seed. Load each neighbor through the existing `retrieval_records` identity and return it with:

```python
ChannelScore(
    channel="structural_context",
    score=Decimal("1"),
    detail=f"seed:{seed.evidence_id}",
)
```

If the seed is not an `elements` row (for example a table or visual), return `()` rather than guessing a structure.

- [ ] **Step 4: Add the context fusion weight and two-pass bundle flow**

Add:

```python
"structural_context": Decimal("0.08"),
```

In `build_evidence_bundle()`:

1. fuse lexical/structured/graph channels to obtain ranked seeds;
2. take at most the first `limit` seeds;
3. call `load_adjacent_element_hits(..., radius=1)` for each seed;
4. fuse seeds + context channels again;
5. truncate to `limit` only after the second fusion.

This makes context separately cited and lower-ranked than direct entity/numeric matches.

- [ ] **Step 5: Run retrieval suites**

```powershell
python -m pytest -v tests/unit/retrieval tests/integration/retrieval
```

Expected: PASS; no bbox/source identity regression.

- [ ] **Step 6: Commit**

```powershell
git add src/ansim_review/retrieval/index.py src/ansim_review/retrieval/fusion.py src/ansim_review/retrieval/bundle.py tests/integration/retrieval/test_korean_formal_review_retrieval.py
git commit -m "feat: add cited structural retrieval context (#95)"
```

---

### Task 4: Make confidence input evidence-aware

**Files:**
- Modify: `src/ansim_review/review_question.py`
- Modify: `tests/unit/review_question/test_request_builder.py`

**Interfaces:**
- Consumes: evidence bundle `hits`.
- Produces: `_confidence_input_for_bundle(bundle: Mapping[str, object]) -> dict[str, object]` used by `build_review_run_request()`.
- Keep the existing factor names from `FACTOR_WEIGHTS` exactly unchanged.

- [ ] **Step 1: Write the zero-evidence RED test**

Add:

```python
def test_builder_does_not_assign_full_confidence_to_zero_evidence() -> None:
    from ansim_review.review_question import build_review_run_request

    bundle = _bundle()
    bundle["hits"] = []

    request = build_review_run_request(bundle)
    factors = request["confidence_input"]["factors"]

    assert factors["source completeness"]["value"] == "0.0"
    assert factors["traceability"]["value"] == "0.0"
    assert factors["input completeness"]["value"] == "0.0"
    assert all(item["source"] == "retrieval:evidence_availability" for item in factors.values())
```

Add a companion test that a non-empty traceable bundle preserves the current nominal `1.0` values until later stages refine confidence.

- [ ] **Step 2: Run and verify RED**

```powershell
python -m pytest -v tests/unit/review_question/test_request_builder.py
```

Expected: zero-evidence assertion fails because current code sets every factor to `1.0`.

- [ ] **Step 3: Implement the minimal evidence-aware mapping**

Use these exact values:

- if `hits` is empty: `source completeness`, `traceability`, and `input completeness` = `"0.0"`; all other factors = `"1.0"`;
- if at least one traceable hit exists: retain `"1.0"` for all factors;
- every factor source for this initial request becomes `retrieval:evidence_availability`.

Do not invent quality scores from rank/count in this issue.

- [ ] **Step 4: Run unit + review-question integration tests**

```powershell
python -m pytest -v tests/unit/review_question/test_request_builder.py tests/integration/review_question
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/ansim_review/review_question.py tests/unit/review_question/test_request_builder.py
git commit -m "fix: fail confidence closed on zero evidence (#95)"
```

---

### Task 5: Prohibit vacuous Track B ACCEPT

**Files:**
- Modify: `src/ansim_review/llm_layer/track_b.py`
- Modify: `tests/unit/llm_layer/test_track_b_validator.py`

**Interfaces:**
- Consumes: validated Track A draft and Track B JSON.
- Produces: same `TrackBAudit` type; no schema/version change.
- Empty Track A claim set requires `overall_disposition="INCOMPLETE"`; `ACCEPT` is invalid.

- [ ] **Step 1: Write failing empty-claims tests**

Construct a valid `ValidatedTrackA` with `draft.claims == ()` and assert:

```python
with pytest.raises(ValueError, match="empty Track A claim set must be INCOMPLETE"):
    validate_track_b_output(
        {
            "run_id": track_a.draft.run_id,
            "claim_audits": [],
            "overall_disposition": "ACCEPT",
        },
        track_a,
    )
```

Then assert the same empty audit with `overall_disposition="INCOMPLETE"` returns a `TrackBAudit` whose overall disposition is `INCOMPLETE`.

- [ ] **Step 2: Run and verify RED**

```powershell
python -m pytest -v tests/unit/llm_layer/test_track_b_validator.py
```

Expected: current empty `ACCEPT` test path is accepted and the new assertion fails.

- [ ] **Step 3: Implement the explicit empty-set rule**

Before `_derive_overall()` normal handling:

```python
if not expected_claim_ids:
    if payload.get("claim_audits") not in ([], ()):
        raise ValueError("empty Track A claim set cannot contain claim audits")
    overall = _string(payload.get("overall_disposition"), "overall_disposition")
    if overall != "INCOMPLETE":
        raise ValueError("empty Track A claim set must be INCOMPLETE")
    return TrackBAudit(
        run_id=run_id,
        claim_audits=(),
        overall_disposition="INCOMPLETE",
    )
```

Keep non-empty claim coverage rules unchanged.

- [ ] **Step 4: Run Track A/B unit suites**

```powershell
python -m pytest -v tests/unit/llm_layer/test_track_a_validator.py tests/unit/llm_layer/test_track_b_validator.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/ansim_review/llm_layer/track_b.py tests/unit/llm_layer/test_track_b_validator.py
git commit -m "fix: reject vacuous Track B acceptance (#95)"
```

---

### Task 6: Preserve snapshot and Track A missing-input lineage in final packets

**Files:**
- Modify: `src/ansim_review/contracts/review.py`
- Modify: `src/ansim_review/contracts/codecs.py`
- Modify: `src/ansim_review/abstention/finalizer.py`
- Modify: `tests/integration/abstention/test_finalizer.py`

**Interfaces:**
- Consumes: `TrackABundle.inputs["snapshot_hash"]` and `ValidatedTrackA.draft.missing_inputs`.
- Produces: legacy `ReviewPacket` gains `snapshot_sha256: str | None = None` and `missing_inputs: tuple[str, ...] = ()`; new packets emit both fields, old packet JSON may omit both and still decode.
- Do not migrate the whole formal-review finalizer to `ReviewPacketV2` in #95; that would introduce unrelated case/rule/formula-manifest requirements.

- [ ] **Step 1: Write failing finalizer lineage tests**

Extend the existing finalizer fixture so the Track A bundle has:

```python
"inputs": {"snapshot_hash": "a" * 64}
```

and Track A output has a deterministic missing input such as:

```python
"missing_inputs": ["청소년문화의집 적용대상 확인"]
```

Assert `finalize_run()` produces:

```python
assert packet.snapshot_sha256 == "a" * 64
assert packet.missing_inputs == ("청소년문화의집 적용대상 확인",)
```

Assert the serialized `final-review-packet.json` contains the same fields.

Add a codec compatibility test using an old packet fixture without these fields and assert decode returns `snapshot_sha256 is None` and `missing_inputs == ()`.

- [ ] **Step 2: Run and verify RED**

```powershell
python -m pytest -v tests/integration/abstention/test_finalizer.py
```

Expected: `ReviewPacket` lacks the fields.

- [ ] **Step 3: Extend the legacy dataclass and decoder compatibly**

Append defaulted fields to `ReviewPacket`:

```python
snapshot_sha256: str | None = None
missing_inputs: tuple[str, ...] = ()
```

In `decode_review_packet()` add both to the allowed field set, but decode absent values as `None` / `()` so historical packets remain readable. Validate a present snapshot as a 64-character SHA-256 using existing validation helpers or the same strict pattern already used elsewhere.

- [ ] **Step 4: Derive lineage only from manifest-bound data in the finalizer**

In `expected_final_review_packet()`:

1. read `snapshot_hash` from `bundle.inputs`;
2. require it to be a 64-character lowercase SHA-256 when present; for formal review-question bundles it must be present;
3. derive `missing_inputs` as sorted unique values from `validated_a.draft.missing_inputs` plus all `bundle.rules[*].missing_inputs`;
4. use the same derived tuple for `missing_required_input` gate evaluation and the packet field.

Update `review_packet_document()` to emit:

```python
"snapshot_sha256": packet.snapshot_sha256,
"missing_inputs": list(packet.missing_inputs),
```

- [ ] **Step 5: Run finalizer and codec-related suites**

```powershell
python -m pytest -v tests/integration/abstention tests/unit/contracts tests/integration/review_run
```

Expected: PASS; historical packet fixtures continue to decode.

- [ ] **Step 6: Commit**

```powershell
git add src/ansim_review/contracts/review.py src/ansim_review/contracts/codecs.py src/ansim_review/abstention/finalizer.py tests/integration/abstention/test_finalizer.py
git commit -m "fix: preserve formal review packet lineage (#95)"
```

---

### Task 7: Make Review Workspace summary match finalizer missing-input state

**Files:**
- Modify: `src/ansim_review/review_packet/builder.py`
- Modify: `tests/unit/review_packet/test_builder.py`
- Modify: `tests/integration/review_packet/test_html_renderer.py` only if the existing summary copy needs an assertion update.

**Interfaces:**
- Consumes: packet-level `missing_inputs` from Task 6.
- Produces: `model["summary"]["missing_input_count"]` counts the packet-level deduplicated set and `model["metadata"]["snapshot_sha256"]` is the final packet snapshot hash.

- [ ] **Step 1: Write the failing projection test**

Using a final packet with:

```json
{
  "status": "ABSTAIN",
  "snapshot_sha256": "aaaaaaaa...",
  "missing_inputs": ["청소년문화의집 적용대상 확인"],
  "abstention_reasons": ["MISSING_REQUIRED_INPUT"]
}
```

assert:

```python
model = build_review_view_model(packet, evidence_db)
assert model["summary"]["missing_input_count"] == 1
assert model["metadata"]["snapshot_sha256"] == "a" * 64
assert model["missing_inputs"] == ["청소년문화의집 적용대상 확인"]
```

- [ ] **Step 2: Run and verify RED**

```powershell
python -m pytest -v tests/unit/review_packet/test_builder.py
```

Expected: current builder reports `missing_input_count == 0` when rules have no missing inputs.

- [ ] **Step 3: Make packet-level missing inputs authoritative for the projection**

Add a helper:

```python
def _packet_missing_inputs(document: Mapping[str, object], rules: Sequence[Mapping[str, object]]) -> list[str]:
    explicit = _strings(document.get("missing_inputs", []), "missing_inputs")
    rule_values = [
        value
        for rule in rules
        for value in _strings(rule.get("missing_inputs", []), "missing_inputs")
    ]
    return sorted(set(explicit) | set(rule_values))
```

Pass this list into `_summary()` rather than recomputing rule-only missing inputs inside `_summary()`, expose it as `model["missing_inputs"]`, and retain existing v2 behavior by treating absent legacy `missing_inputs` as `[]`.

- [ ] **Step 4: Run builder + HTML suites**

```powershell
python -m pytest -v tests/unit/review_packet/test_builder.py tests/integration/review_packet/test_html_renderer.py tests/integration/review_packet/test_review_workspace_ui.py
```

Expected: PASS; default nondeveloper UI still hides raw hashes outside audit disclosure.

- [ ] **Step 5: Commit**

```powershell
git add src/ansim_review/review_packet/builder.py tests/unit/review_packet/test_builder.py tests/integration/review_packet/test_html_renderer.py
git commit -m "fix: align review summary with missing inputs (#95)"
```

---

### Task 8: Eliminate normal-path Track A same-file `FILEEXISTSERROR`

**Files:**
- Modify: `src/ansim_review/review_run.py`
- Modify: `tests/unit/review_question/test_track_a_submission.py`
- Modify: `tests/integration/review_question/test_review_metrics.py`

**Interfaces:**
- Consumes: validated Track A source `Path` and canonical destination `runs/<run-id>/track-a-output.json`.
- Produces: `_publish_validated_track_a(source: Path, destination: Path, document: object) -> None` with explicit same-path and create-only behavior.

- [ ] **Step 1: Reproduce the observed same-path failure**

Add a test that prepares a run, writes a valid but pretty-printed Track A JSON directly to the canonical `run_directory / "track-a-output.json"`, then calls:

```python
result = submit_track_a(
    workspace,
    prepared.run_id,
    prepared.run_directory / "track-a-output.json",
)
```

Assert it returns `SubmittedTrackA`, creates `next-action-track-b.json`, and does not alter the original Track A file bytes.

Add a second test where a different external source is submitted after a conflicting canonical Track A exists; assert `FileExistsError("existing artifact differs: track-a-output.json")` remains.

- [ ] **Step 2: Run and verify RED**

```powershell
python -m pytest -v tests/unit/review_question/test_track_a_submission.py
```

Expected: same-path pretty JSON reproduces the current `FILEEXISTSERROR` because canonical JSON bytes differ from the already-present source bytes.

- [ ] **Step 3: Implement same-path idempotent publication without overwrite**

Add:

```python
def _publish_validated_track_a(
    source: Path,
    destination: Path,
    document: object,
) -> None:
    if source.resolve() == destination.resolve():
        if not destination.is_file():
            raise FileNotFoundError(destination)
        return
    _write_json_or_identical(destination, document)
```

Call it only **after** `validate_track_a_submission()` succeeds. This means the canonical same-path file is accepted in place only after structural/numeric validation; no rewrite occurs. Different-path publication retains the existing canonical create-or-identical contract.

- [ ] **Step 4: Add retry metric regression**

In `test_review_metrics.py`, execute the normal same-path Track A flow and assert derived metrics show:

```python
assert metrics["retry_count"] == 0
assert not any(
    stage["reason_code"] == "FILEEXISTSERROR"
    for stage in metrics["stages"]
)
```

- [ ] **Step 5: Run review-question focused suites**

```powershell
python -m pytest -v tests/unit/review_question tests/integration/review_question
```

Expected: PASS, including retry count 0 for the valid flow.

- [ ] **Step 6: Commit**

```powershell
git add src/ansim_review/review_run.py tests/unit/review_question/test_track_a_submission.py tests/integration/review_question/test_review_metrics.py
git commit -m "fix: make validated Track A same-path submission idempotent (#95)"
```

---

### Task 9: Add the representative formal-review regression across retrieval → packet

**Files:**
- Modify: `tests/integration/review_question/test_review_question_cli.py`
- Reuse: `tests/integration/retrieval/test_korean_formal_review_retrieval.py`

**Interfaces:**
- Consumes: all Tasks 1–8.
- Produces: one deterministic integration regression for the exact Korean question proving relevant evidence survives into `review-request.json` / `track-a-bundle.json`, with no manual expansion required.

- [ ] **Step 1: Add a failing/guarding integration scenario**

Use a workspace fixture with the four parser-ordered evidence elements from Task 3 and run:

```powershell
python -m evidence_review review-question prepare `
  --workspace <fixture-workspace> `
  --question "청소년 문화의집은 면적이 1500제곱미터 이상이어야 한다."
```

The test should invoke the CLI programmatically/subprocess using the repository’s existing helper pattern and assert:

```python
assert result.returncode == 0
assert review_request["evidence"]
texts = [item["text"] for item in review_request["evidence"]]
assert any("청소년문화의집" in text for text in texts)
assert any("1,500제곱미터" in text and "청소년수련관" in " ".join(texts) for text in texts)
assert review_request["inputs"]["snapshot_hash"] == snapshot_hash
assert all(
    item["value"] != "1.0"
    for name, item in zero_evidence_request["confidence_input"]["factors"].items()
    if name in {"source completeness", "traceability", "input completeness"}
)
```

For the positive run, do not assert a machine final truth value; Track A/B remain external and the human owns the final decision.

- [ ] **Step 2: Run the focused formal-review matrix**

```powershell
python -m pytest -v `
  tests/unit/retrieval `
  tests/integration/retrieval `
  tests/unit/review_question `
  tests/integration/review_question `
  tests/unit/llm_layer/test_track_b_validator.py `
  tests/integration/abstention/test_finalizer.py `
  tests/unit/review_packet/test_builder.py `
  tests/integration/review_packet/test_html_renderer.py
```

Expected: PASS.

- [ ] **Step 3: Commit the integration regression**

```powershell
git add tests/integration/review_question/test_review_question_cli.py tests/integration/retrieval/test_korean_formal_review_retrieval.py
git commit -m "test: cover Korean formal review retrieval regression (#95)"
```

---

### Task 10: Repository-wide verification and #95 evidence record

**Files:**
- Modify: `docs/acceptance/issue-87/README.md` only to append #95 implementation/verification status and exact HEAD; do not mark #93/#87 complete.
- No production code changes unless a failing gate exposes a real regression, in which case return to the owning task and use systematic-debugging before changing code.

**Interfaces:**
- Consumes: exact final `main` HEAD after Tasks 1–9.
- Produces: fresh local verification evidence; no claim about GitHub Actions unless an actual workflow run is observed.

- [ ] **Step 1: Record exact repository state**

```powershell
git rev-parse HEAD
git status --short
git rev-parse origin/main
```

Expected: HEAD == origin/main and worktree clean before acceptance commands.

- [ ] **Step 2: Run focused #95 tests on Python 3.11**

```powershell
$py311 = ".\.venv-acceptance-311\Scripts\python.exe"

& $py311 -m pytest -v `
  tests\unit\retrieval `
  tests\integration\retrieval `
  tests\unit\review_question `
  tests\integration\review_question `
  tests\unit\llm_layer\test_track_b_validator.py `
  tests\integration\abstention\test_finalizer.py `
  tests\unit\review_packet\test_builder.py
```

Expected: exit 0.

- [ ] **Step 3: Run repository-wide Python 3.11 gates**

```powershell
& $py311 -m pytest -v
& $py311 -m ruff check src tests
& $py311 -m mypy src
& $py311 -m compileall -q src scripts web_runtime tests
```

Expected: every command exit 0. Record exact passed/skipped counts rather than assuming the previous `1237 passed, 1 skipped` total remains unchanged.

- [ ] **Step 4: Run the same full/static gates on Python 3.13**

```powershell
$py313 = ".\.venv-acceptance-313\Scripts\python.exe"

& $py313 -m pytest -v
& $py313 -m ruff check src tests
& $py313 -m mypy src
& $py313 -m compileall -q src scripts web_runtime tests
```

Expected: every command exit 0.

- [ ] **Step 5: Run fresh documentation integrity**

Use fresh output paths so a pre-existing report cannot cause an output collision:

```powershell
New-Item -ItemType Directory -Force .acceptance\issue-95 | Out-Null
Remove-Item .acceptance\issue-95\documentation-integrity.json -ErrorAction SilentlyContinue

.\.venv-acceptance-311\Scripts\evidence-review.exe documentation validate `
  --repository-root . `
  --config documentation-integrity.json `
  --output .acceptance\issue-95\documentation-integrity.json
```

Expected: `Documentation integrity: PASS`, errors 0. Warnings may remain and must be recorded exactly.

- [ ] **Step 6: Update the #87 acceptance log without closing integration gates**

Append:

```markdown
### Issue #95 — Korean retrieval / formal-review invariants

- Exact HEAD: `<actual SHA>`
- Focused tests: `<actual result>`
- Python 3.11 full pytest: `<actual result>`
- Python 3.13 full pytest: `<actual result>`
- Ruff: `<actual result>`
- mypy: `<actual result>`
- compileall: `<actual result>`
- documentation integrity: `<actual result>`
- Real Windows protected-browser / 3-run p50/p95 acceptance: remains under #93/#90; not claimed here.
- GitHub Actions: record actual observed state only.
```

Replace angle-bracket values with the actual results from Steps 1–5; do not commit placeholders.

- [ ] **Step 7: Commit acceptance evidence**

```powershell
git add docs/acceptance/issue-87/README.md
git commit -m "docs: record issue 95 verification evidence"
```

- [ ] **Step 8: Verification-before-completion gate**

Invoke `superpowers:verification-before-completion`, re-check the exact final HEAD and fresh command outputs, then comment on #95 with the actual results. Close #95 as `completed` only if all #95 acceptance criteria are evidenced. Keep #90, #89, #92, #94, #93, and #87 open unless their own remaining manual acceptance criteria have independently passed.
