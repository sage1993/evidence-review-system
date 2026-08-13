# Korean Retrieval and Formal Review Invariants Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Korean natural-language formal-review questions retrieve relevant traceable evidence despite spacing/particle/numeric-format differences, and make zero-evidence/zero-claim, missing-input, snapshot-lineage, and Track A retry behavior fail closed and internally consistent.

**Architecture:** Keep SQLite FTS5 and add a deterministic Korean query-variant layer with bounded `entity`, `numeric`, and `concept` groups. Each group uses a separate weighted channel so multi-group evidence ranks higher without unrestricted token OR; structural context is returned as separately cited adjacent evidence rather than concatenated uncited text. Downstream changes derive confidence from evidence availability, prohibit vacuous Track B acceptance, carry snapshot/missing-input lineage through the compatible legacy review packet, and accept an already-canonical Track A source path only after successful validation.

**Tech Stack:** Python 3.11/3.13, stdlib `re`/`unicodedata`, SQLite FTS5 (`unicode61`), existing `ansim_review` contracts/retrieval/finalizer/review-packet modules, pytest, Ruff, mypy. No new runtime dependency and no model/API query rewriting.

## Global Constraints

- Work directly on `main`; do not create a feature branch for this tranche.
- All questions stay on the formal retrieval → Track A → Track A validation → Track B → final packet path; no quick-review mode.
- Keep runtime execution offline; add no network/model/API calls.
- Never replace grouped retrieval with unrestricted token OR.
- Every returned seed/context record retains its own document/revision/page/evidence/bbox/source-hash citation identity.
- Parser output and evidence source authority remain immutable.
- Historical legacy review packets that omit the new lineage fields must remain readable.
- Track A create-only immutability remains authoritative; a differing existing artifact is always an error.
- Windows is the primary acceptance platform; Python 3.11 and 3.13 final E2E remains under #93.
- GitHub Actions status is separate from local Windows validation.

---

## File Structure

- Create `src/ansim_review/retrieval/korean_variants.py` — bounded deterministic Korean decomposition only.
- Modify `src/ansim_review/retrieval/index.py` — named literal grouped channels and adjacent-element lookup.
- Modify `src/ansim_review/retrieval/fusion.py` — grouped/context weights.
- Modify `src/ansim_review/retrieval/bundle.py` — grouped retrieval, context expansion, query trace export.
- Modify `src/ansim_review/review_question.py` — evidence-aware initial confidence.
- Modify `src/ansim_review/llm_layer/track_b.py` — zero-claim `ACCEPT` prohibition.
- Modify `src/ansim_review/contracts/review.py` — optional legacy packet snapshot/missing-input fields.
- Modify `src/ansim_review/contracts/codecs.py` — backward-compatible decoding.
- Modify `src/ansim_review/abstention/finalizer.py` — manifest-bound lineage derivation.
- Modify `src/ansim_review/review_packet/builder.py` — packet-level missing-input projection.
- Modify `src/ansim_review/review_packet/presentation.py` — packet-level missing-input text in 추가 확인.
- Modify `src/ansim_review/review_run.py` — same-path validated Track A publication.
- Create `tests/unit/retrieval/test_korean_variants.py`.
- Modify `tests/integration/retrieval/test_fts_lexical_channels.py`.
- Create `tests/integration/retrieval/test_korean_formal_review_retrieval.py`.
- Modify `tests/unit/review_question/test_request_builder.py`.
- Modify `tests/unit/llm_layer/test_track_b_validator.py`.
- Modify `tests/integration/abstention/test_finalizer.py`.
- Modify `tests/unit/review_packet/test_builder.py`.
- Modify `tests/integration/review_packet/test_html_renderer.py` only for the new missing-input UI assertion.
- Modify `tests/unit/review_question/test_track_a_submission.py`.
- Modify `tests/integration/review_question/test_review_metrics.py`.
- Modify `tests/integration/review_question/test_review_question_cli.py` for the representative question regression.

---

### Task 1: Deterministic Korean grouped query variants

**Files:**
- Create: `src/ansim_review/retrieval/korean_variants.py`
- Create: `tests/unit/retrieval/test_korean_variants.py`

**Interfaces:**
- Consumes: primary question `str`.
- Produces: `GroupedQueryVariants(entity: tuple[str, ...], numeric: tuple[str, ...], concept: tuple[str, ...])` and `derive_korean_query_variants(primary: str) -> GroupedQueryVariants`.

- [ ] **Step 1: Write the RED regression for the real question**

```python
from ansim_review.retrieval.korean_variants import derive_korean_query_variants


def test_real_question_derives_bounded_groups() -> None:
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

Add two more tests: repeated calls return exactly equal tuples, and `"기준을 확인한다."` produces no numeric variants.

- [ ] **Step 2: Run RED**

```powershell
python -m pytest -v tests/unit/retrieval/test_korean_variants.py
```

Expected: import/collection failure because the module is absent.

- [ ] **Step 3: Implement the exact public interface**

```python
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GroupedQueryVariants:
    entity: tuple[str, ...]
    numeric: tuple[str, ...]
    concept: tuple[str, ...]


def derive_korean_query_variants(primary: str) -> GroupedQueryVariants:
    ...
```

Implementation contract:

1. Reuse the same NFC/whitespace normalization semantics as `retrieval.query.normalize_text()`.
2. Remove terminal sentence punctuation before token analysis.
3. Strip Korean suffixes only when a stem of at least two characters remains. Use this fixed suffix tuple sorted by descending length before matching: `이어야`, `여야`, `에서`, `으로`, `한다`, `은`, `는`, `이`, `가`, `을`, `를`, `에`, `로`, `와`, `과`, `도`.
4. The entity subject is the non-empty stripped token sequence before the first measurement/constraint token. Emit the spaced phrase first, then its whitespace-free form if different.
5. Numeric regex: `(?P<number>\d[\d,]*)(?P<unit>제곱미터|㎡)?`. Emit comma-free and grouped forms, followed by the same forms with the detected unit.
6. Bounded concept map only:

```python
_CONCEPT_VARIANTS = {
    "면적": ("면적", "연면적", "연건축면적"),
    "연면적": ("면적", "연면적", "연건축면적"),
    "연건축면적": ("면적", "연면적", "연건축면적"),
    "이상": ("이상",),
    "이하": ("이하",),
}
```

7. Preserve first-occurrence ordering with an ordered-dedup helper; never use unordered set iteration for output.
8. Do not emit arbitrary sentence tokens as fallback variants.

- [ ] **Step 4: Run GREEN**

```powershell
python -m pytest -v tests/unit/retrieval/test_korean_variants.py tests/unit/retrieval/test_query_normalization.py
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/ansim_review/retrieval/korean_variants.py tests/unit/retrieval/test_korean_variants.py
git commit -m "feat: derive deterministic Korean query variants (#95)"
```

---

### Task 2: Grouped FTS channels and multi-group fusion

**Files:**
- Modify: `src/ansim_review/retrieval/index.py`
- Modify: `src/ansim_review/retrieval/fusion.py`
- Modify: `src/ansim_review/retrieval/bundle.py`
- Modify: `tests/integration/retrieval/test_fts_lexical_channels.py`

**Interfaces:**
- Consumes: Task 1 grouped variants.
- Produces: `search_fts_literal(connection, query, *, channel, limit=20) -> tuple[RetrievalHit, ...]`, limited to `fts_entity`, `fts_numeric`, `fts_concept`.
- Bundle query metadata gains `derived_variants` with the three ordered arrays.

- [ ] **Step 1: Add failing grouped-channel tests**

Extend the fixture with:

```python
facility = "청소년문화의집은 다양한 유형의 청소년수련시설 중 가장 작은 규모의 시설"
criterion = "청소년수련관은 연건축면적이 1,500제곱미터 이상이어야 한다"
```

For the real question assert both evidence IDs are retrieved, `facility` has an `fts_entity` channel, `criterion` has `fts_numeric` and `fts_concept`, and:

```python
assert bundle["query"]["derived_variants"] == {
    "entity": ["청소년 문화의집", "청소년문화의집"],
    "numeric": ["1500", "1,500", "1500제곱미터", "1,500제곱미터"],
    "concept": ["면적", "연면적", "연건축면적", "이상"],
}
assert all(
    score["channel"] != "fts_token_or"
    for hit in bundle["hits"]
    for score in hit["channel_scores"]
)
```

- [ ] **Step 2: Run RED**

```powershell
python -m pytest -v tests/integration/retrieval/test_fts_lexical_channels.py
```

Expected: no relevant Korean grouped hits / no `derived_variants`.

- [ ] **Step 3: Add bounded literal FTS helper**

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

Do not expose raw caller-provided FTS expressions.

- [ ] **Step 4: Add fusion weights**

```python
"fts_entity": Decimal("0.40"),
"fts_numeric": Decimal("0.20"),
"fts_concept": Decimal("0.10"),
```

Because `RetrievalHit.with_channel()` merges duplicate scores by channel, multiple variants in one group do not multiply weight; evidence matching multiple different groups accumulates weight.

- [ ] **Step 5: Wire grouped variants into `bundle.py`**

Add:

```python
def _derived_variant_hits(
    connection: sqlite3.Connection,
    primary: str,
    limit: int,
) -> tuple[tuple[RetrievalHit, ...], ...]:
    ...
```

Call `search_fts_literal()` per variant; rewrite score detail to `derived:entity:<term>`, `derived:numeric:<term>`, or `derived:concept:<term>`. Append these channels after existing primary/synonym/user/LLM channels, before fusion. Export `derived_variants` in `bundle["query"]`.

- [ ] **Step 6: Run regression suites**

```powershell
python -m pytest -v `
  tests/unit/retrieval/test_korean_variants.py `
  tests/unit/retrieval/test_query_normalization.py `
  tests/integration/retrieval/test_fts_lexical_channels.py `
  tests/integration/retrieval/test_fts_retrieval.py `
  tests/integration/retrieval/test_hybrid_fusion.py
```

Expected: PASS.

- [ ] **Step 7: Commit**

```powershell
git add src/ansim_review/retrieval/index.py src/ansim_review/retrieval/fusion.py src/ansim_review/retrieval/bundle.py tests/integration/retrieval/test_fts_lexical_channels.py
git commit -m "feat: add grouped Korean retrieval channels (#95)"
```

---

### Task 3: Separately cited structural context

**Files:**
- Modify: `src/ansim_review/retrieval/index.py`
- Modify: `src/ansim_review/retrieval/fusion.py`
- Modify: `src/ansim_review/retrieval/bundle.py`
- Create: `tests/integration/retrieval/test_korean_formal_review_retrieval.py`

**Interfaces:**
- Consumes: fused seed `RetrievalHit` values.
- Produces: `load_adjacent_element_hits(connection, seed, *, radius=1) -> tuple[RetrievalHit, ...]` with channel `structural_context`.
- Context never changes the seed text/citation; each neighbor remains a separate cited hit.

- [ ] **Step 1: Create RED fixture with parser order**

Use one `EvidenceSnapshot` page with:

```text
E-ROW-LABEL       parser_order=10  청소년수련관
E-ROW-CRITERION   parser_order=11  연건축면적이 1,500제곱미터 이상이어야 하며 ...
E-CULTURE-LABEL   parser_order=20  청소년문화의집
E-CULTURE-DESC    parser_order=21  다양한 유형의 청소년수련시설 중 가장 작은 규모의 시설 ...
```

After `build_fts_index()`, run the real question and assert the returned cited evidence IDs include all four records. For every hit assert `hit["citation"]["evidence_id"] == hit["evidence_id"]`. Add a second page and assert adjacency never crosses page/revision boundaries.

- [ ] **Step 2: Run RED**

```powershell
python -m pytest -v tests/integration/retrieval/test_korean_formal_review_retrieval.py
```

Expected: direct seeds may exist, but row-label/description context is missing.

- [ ] **Step 3: Implement page-local neighbor loading**

Resolve the seed in `elements` to `page_id` + `parser_order`; query only the same page and only element rows with parser order from `seed_order - radius` through `seed_order + radius`, excluding the seed. Resolve each neighbor from `retrieval_records` and return it with:

```python
ChannelScore(
    channel="structural_context",
    score=Decimal("1"),
    detail=f"seed:{seed.evidence_id}",
)
```

If the seed is not an `elements` record, return `()`.

- [ ] **Step 4: Add low context weight and two-pass fusion**

```python
"structural_context": Decimal("0.08"),
```

Bundle flow becomes: direct channels → first fusion/ranking → adjacent contexts for at most the first `limit` seeds → second fusion → final `limit`. Never concatenate neighbor text into the seed citation.

- [ ] **Step 5: Run all retrieval tests**

```powershell
python -m pytest -v tests/unit/retrieval tests/integration/retrieval
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/ansim_review/retrieval/index.py src/ansim_review/retrieval/fusion.py src/ansim_review/retrieval/bundle.py tests/integration/retrieval/test_korean_formal_review_retrieval.py
git commit -m "feat: add cited structural retrieval context (#95)"
```

---

### Task 4: Evidence-aware initial confidence

**Files:**
- Modify: `src/ansim_review/review_question.py`
- Modify: `tests/unit/review_question/test_request_builder.py`

**Interfaces:**
- Produces: `_confidence_input_for_bundle(bundle: Mapping[str, object]) -> dict[str, object]`.
- Factor names remain exactly those in `FACTOR_WEIGHTS`.

- [ ] **Step 1: Add RED tests**

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
    assert all(
        factor["source"] == "retrieval:evidence_availability"
        for factor in factors.values()
    )
```

Add a companion test that `_bundle()` with a valid traceable hit keeps all initial factor values at `"1.0"`.

- [ ] **Step 2: Run RED**

```powershell
python -m pytest -v tests/unit/review_question/test_request_builder.py
```

Expected: zero-evidence factor assertions fail.

- [ ] **Step 3: Implement minimal evidence-aware values**

If `hits == []`, set only `source completeness`, `traceability`, and `input completeness` to `"0.0"`; all other factors stay `"1.0"`. If at least one traceable hit exists, all remain `"1.0"`. Set every source string to `retrieval:evidence_availability`. Do not invent rank/count-based quality scoring in #95.

- [ ] **Step 4: Run unit + integration**

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
- Same `TrackBAudit` schema.
- Empty Track A claim set requires `overall_disposition="INCOMPLETE"`; `ACCEPT` is invalid.

- [ ] **Step 1: Add RED tests**

Build a valid `ValidatedTrackA` with `draft.claims == ()`, then:

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

Assert the same empty audit with `overall_disposition="INCOMPLETE"` returns a `TrackBAudit` with `INCOMPLETE`.

- [ ] **Step 2: Run RED**

```powershell
python -m pytest -v tests/unit/llm_layer/test_track_b_validator.py
```

Expected: current empty `ACCEPT` is accepted.

- [ ] **Step 3: Implement explicit empty-set semantics**

After validating `run_id`, before normal claim-audit iteration:

```python
if not expected_claim_ids:
    audits_value = _sequence(payload.get("claim_audits"), "claim_audits")
    if audits_value:
        raise ValueError("empty Track A claim set cannot contain claim audits")
    overall = _string(payload.get("overall_disposition"), "overall_disposition")
    if overall != "INCOMPLETE":
        raise ValueError("empty Track A claim set must be INCOMPLETE")
    return TrackBAudit(run_id=run_id, claim_audits=(), overall_disposition="INCOMPLETE")
```

Keep non-empty coverage rules unchanged.

- [ ] **Step 4: Run Track A/B tests**

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

### Task 6: Preserve snapshot and missing-input lineage in legacy final packets

**Files:**
- Modify: `src/ansim_review/contracts/review.py`
- Modify: `src/ansim_review/contracts/codecs.py`
- Modify: `src/ansim_review/abstention/finalizer.py`
- Modify: `tests/integration/abstention/test_finalizer.py`

**Interfaces:**
- Legacy `ReviewPacket` gains defaulted `snapshot_sha256: str | None = None` and `missing_inputs: tuple[str, ...] = ()` at the end of the dataclass.
- New packets emit the fields; old JSON may omit them.
- Do not migrate this path wholesale to `ReviewPacketV2`; #95 does not introduce case/rule/formula-manifest requirements.

- [ ] **Step 1: Add RED lineage/compatibility tests**

Use a Track A bundle with `inputs={"snapshot_hash": "a" * 64}` and Track A output with `missing_inputs=["청소년문화의집 적용대상 확인"]`. Assert:

```python
assert packet.snapshot_sha256 == "a" * 64
assert packet.missing_inputs == ("청소년문화의집 적용대상 확인",)
```

Assert serialized `final-review-packet.json` contains both fields. Add an old-packet decode fixture without either field and assert `snapshot_sha256 is None` and `missing_inputs == ()`.

- [ ] **Step 2: Run RED**

```powershell
python -m pytest -v tests/integration/abstention/test_finalizer.py
```

Expected: `ReviewPacket` has no new fields.

- [ ] **Step 3: Extend dataclass/codec backward compatibly**

Append:

```python
snapshot_sha256: str | None = None
missing_inputs: tuple[str, ...] = ()
```

Add both keys to `decode_review_packet()` allowed fields. Missing fields decode to defaults. A present snapshot must match lowercase `[0-9a-f]{64}`; reject invalid values.

- [ ] **Step 4: Derive both values from manifest-bound artifacts**

In `expected_final_review_packet()`:

- obtain `snapshot_hash` from `bundle.inputs` and validate it;
- derive `missing_inputs = tuple(sorted(set(validated_a.draft.missing_inputs) | {item for rule in bundle.rules for item in rule.missing_inputs}))`;
- use `bool(missing_inputs)` for the `missing_required_input` gate;
- pass both fields to `ReviewPacket`.

In `review_packet_document()` emit `snapshot_sha256` and `missing_inputs`.

- [ ] **Step 5: Run finalizer/contract suites**

```powershell
python -m pytest -v tests/integration/abstention tests/unit/contracts tests/integration/review_run
```

Expected: PASS with historical packet compatibility intact.

- [ ] **Step 6: Commit**

```powershell
git add src/ansim_review/contracts/review.py src/ansim_review/contracts/codecs.py src/ansim_review/abstention/finalizer.py tests/integration/abstention/test_finalizer.py
git commit -m "fix: preserve formal review packet lineage (#95)"
```

---

### Task 7: Align Review summary and 추가 확인 with packet missing inputs

**Files:**
- Modify: `src/ansim_review/review_packet/builder.py`
- Modify: `src/ansim_review/review_packet/presentation.py`
- Modify: `tests/unit/review_packet/test_builder.py`
- Modify: `tests/integration/review_packet/test_html_renderer.py`

**Interfaces:**
- Produces: top-level view-model `missing_inputs: list[str]`; `_summary(..., missing_inputs, ...)` uses that same set.
- `additional_review_items()` consumes `model["missing_inputs"]` before rule/reason items.

- [ ] **Step 1: Add RED builder test**

For a legacy packet with `status="ABSTAIN"`, `snapshot_sha256="a" * 64`, `missing_inputs=["청소년문화의집 적용대상 확인"]`, and `abstention_reasons=["MISSING_REQUIRED_INPUT"]`, assert:

```python
model = build_review_view_model(packet, evidence_db)
assert model["summary"]["missing_input_count"] == 1
assert model["metadata"]["snapshot_sha256"] == "a" * 64
assert model["missing_inputs"] == ["청소년문화의집 적용대상 확인"]
```

- [ ] **Step 2: Add RED HTML/presentation assertion**

Render that model and assert both the human missing-input text and the localized hard-gate reason appear in `#additional-review`, while raw snapshot SHA remains only in audit content.

- [ ] **Step 3: Run RED**

```powershell
python -m pytest -v tests/unit/review_packet/test_builder.py tests/integration/review_packet/test_html_renderer.py
```

Expected: missing-input count/text does not reflect Track A packet-level input.

- [ ] **Step 4: Implement one authoritative missing-input projection**

Add:

```python
def _packet_missing_inputs(
    document: Mapping[str, object],
    rules: Sequence[Mapping[str, object]],
) -> list[str]:
    explicit = _strings(document.get("missing_inputs", []), "missing_inputs")
    rule_values = [
        value
        for rule in rules
        for value in _strings(rule.get("missing_inputs", []), "missing_inputs")
    ]
    return sorted(set(explicit) | set(rule_values))
```

Compute it once in `build_review_view_model()`, expose it as `model["missing_inputs"]`, and pass it into `_summary()` for the count. In `presentation.additional_review_items()`, add `model["missing_inputs"]` before rule-specific values and deduplicate with the existing ordered `values` list.

- [ ] **Step 5: Run UI projection suites**

```powershell
python -m pytest -v `
  tests/unit/review_packet/test_builder.py `
  tests/integration/review_packet/test_html_renderer.py `
  tests/integration/review_packet/test_review_workspace_ui.py
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/ansim_review/review_packet/builder.py src/ansim_review/review_packet/presentation.py tests/unit/review_packet/test_builder.py tests/integration/review_packet/test_html_renderer.py
git commit -m "fix: align review summary with missing inputs (#95)"
```

---

### Task 8: Remove normal same-path Track A `FILEEXISTSERROR`

**Files:**
- Modify: `src/ansim_review/review_run.py`
- Modify: `tests/unit/review_question/test_track_a_submission.py`
- Modify: `tests/integration/review_question/test_review_metrics.py`

**Interfaces:**
- Produces: `_publish_validated_track_a(source: Path, destination: Path, document: object) -> None`.
- Same-path source is accepted in place only after `validate_track_a_submission()` succeeds.

- [ ] **Step 1: Reproduce RED**

Prepare a run, write valid pretty-printed Track A JSON directly to `prepared.run_directory / "track-a-output.json"`, preserve `original_bytes`, then call `submit_track_a()` using that same path. Assert it succeeds, creates `next-action-track-b.json`, and `track-a-output.json` bytes still equal `original_bytes`.

Add another test where a different external source is submitted while a conflicting canonical target exists; assert `FileExistsError("existing artifact differs: track-a-output.json")` remains.

- [ ] **Step 2: Run RED**

```powershell
python -m pytest -v tests/unit/review_question/test_track_a_submission.py
```

Expected: same-path pretty JSON reproduces `FILEEXISTSERROR`.

- [ ] **Step 3: Implement validated same-path publication**

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

Call this only after Track A structural/numeric validation returns successfully. Do not overwrite any differing existing destination.

- [ ] **Step 4: Add metric regression**

Execute the normal same-path Track A flow and assert:

```python
assert metrics["retry_count"] == 0
assert not any(
    stage["reason_code"] == "FILEEXISTSERROR"
    for stage in metrics["stages"]
)
```

- [ ] **Step 5: Run review-question suites**

```powershell
python -m pytest -v tests/unit/review_question tests/integration/review_question
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/ansim_review/review_run.py tests/unit/review_question/test_track_a_submission.py tests/integration/review_question/test_review_metrics.py
git commit -m "fix: make validated Track A same-path submission idempotent (#95)"
```

---

### Task 9: Representative formal-review regression and repository-wide verification

**Files:**
- Modify: `tests/integration/review_question/test_review_question_cli.py`
- Modify: `docs/acceptance/issue-87/README.md` after verification only.

**Interfaces:**
- Consumes: Tasks 1–8.
- Proves: the exact Korean question yields relevant cited evidence without `--expansion`, snapshot lineage survives, zero-evidence confidence fails closed, and the valid same-path flow records retry 0.

- [ ] **Step 1: Add deterministic CLI regression using the repository’s existing `tmp_path`/CLI helper pattern**

Build the evidence fixture in `tmp_path`, run the existing CLI entry function/subprocess with arguments equivalent to:

```python
[
    "review-question",
    "prepare",
    "--workspace",
    str(workspace),
    "--question",
    "청소년 문화의집은 면적이 1500제곱미터 이상이어야 한다.",
]
```

Read the generated run’s `evidence-query.json`, `review-request.json`, and `track-a-bundle.json`. Assert:

```python
assert evidence_query["hits"]
texts = [item["text"] for item in review_request["evidence"]]
assert any("청소년문화의집" in text for text in texts)
assert any("1,500제곱미터" in text for text in texts)
assert any("청소년수련관" in text for text in texts)
assert review_request["inputs"]["snapshot_hash"] == snapshot_hash
assert track_a_bundle["inputs"]["snapshot_hash"] == snapshot_hash
assert evidence_query["query"]["derived_variants"]["entity"] == [
    "청소년 문화의집",
    "청소년문화의집",
]
```

Do not assert a final machine truth value; Track A/B remain external and the human owns the final decision.

- [ ] **Step 2: Run the full #95 focused matrix**

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

Expected: exit 0.

- [ ] **Step 3: Commit representative regression**

```powershell
git add tests/integration/review_question/test_review_question_cli.py
git commit -m "test: cover Korean formal review regression (#95)"
```

- [ ] **Step 4: Record exact repository state before global verification**

```powershell
git rev-parse HEAD
git rev-parse origin/main
git status --short
```

Expected: local HEAD equals `origin/main` and `git status --short` is empty after pushing/syncing the commits.

- [ ] **Step 5: Python 3.11 full/static gates**

```powershell
$py311 = ".\.venv-acceptance-311\Scripts\python.exe"
& $py311 -m pytest -v
& $py311 -m ruff check src tests
& $py311 -m mypy src
& $py311 -m compileall -q src scripts web_runtime tests
```

Expected: every command exit 0. Record the actual pytest passed/skipped totals from this HEAD; do not reuse the older `1237 passed, 1 skipped` count.

- [ ] **Step 6: Python 3.13 full/static gates**

```powershell
$py313 = ".\.venv-acceptance-313\Scripts\python.exe"
& $py313 -m pytest -v
& $py313 -m ruff check src tests
& $py313 -m mypy src
& $py313 -m compileall -q src scripts web_runtime tests
```

Expected: every command exit 0.

- [ ] **Step 7: Fresh documentation-integrity gate**

```powershell
New-Item -ItemType Directory -Force .acceptance\issue-95 | Out-Null
Remove-Item .acceptance\issue-95\documentation-integrity.json -ErrorAction SilentlyContinue
.\.venv-acceptance-311\Scripts\evidence-review.exe documentation validate `
  --repository-root . `
  --config documentation-integrity.json `
  --output .acceptance\issue-95\documentation-integrity.json
```

Expected: `Documentation integrity: PASS` and errors 0. Record warnings exactly.

- [ ] **Step 8: Update acceptance record using only observed values**

Append a `### Issue #95 — Korean retrieval / formal-review invariants` subsection to `docs/acceptance/issue-87/README.md` containing the exact final HEAD and exact outputs from Steps 2, 5, 6, and 7. State explicitly that protected-browser QA and three-run p50/p95 remain under #93/#90 and are not claimed by #95. Record GitHub Actions only if an actual workflow status is observed.

- [ ] **Step 9: Commit acceptance record**

```powershell
git add docs/acceptance/issue-87/README.md
git commit -m "docs: record issue 95 verification evidence"
```

- [ ] **Step 10: Verification-before-completion**

Invoke `superpowers:verification-before-completion`. Re-check the final exact HEAD and the fresh verification outputs. Comment on #95 with those observed results and close #95 as `completed` only if every #95 acceptance item is evidenced. Keep #90, #89, #92, #94, #93, and #87 open unless their own remaining acceptance criteria independently pass.
