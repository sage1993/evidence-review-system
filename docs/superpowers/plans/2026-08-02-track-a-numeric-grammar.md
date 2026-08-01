# Track A Numeric Grammar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure every numeric-looking expression in Track A claim text is either an exact supported token or an explicit validation error.

**Architecture:** Replace regex-only extraction with a small deterministic scanner that recognizes the approved ASCII grammar and returns token spans. A second pass detects unconsumed ASCII digits, Unicode numeric characters, malformed grouping, exponent notation, leading-dot decimals, and underscore separators before provenance checks run.

**Tech Stack:** Python 3.11 standard library, dataclasses, `unicodedata`, pytest.

## Global Constraints

- Runtime dependencies remain empty.
- Track A does not calculate, round, localize, or normalize numbers.
- Supported token text is compared byte-for-byte with `numeric_tokens`.
- A supported token must still exist exactly in cited evidence or a referenced successful `CalculationResult`.
- Unsupported numeric syntax is rejected rather than silently ignored.
- Existing valid integers, decimals, percentages, signed values, and thousands-grouped values remain valid.

---

## File Map

### Create

- `src/ansim_review/llm_layer/numeric_grammar.py`: scanner, spans, and unsupported-syntax detection.
- `tests/unit/llm_layer/test_numeric_grammar.py`: complete grammar matrix.

### Modify

- `src/ansim_review/llm_layer/validators.py`: consume the scanner and expose stable errors.
- `tests/unit/llm_layer/test_track_a_validator.py`: claim-level bypass and provenance regression tests.
- `src/ansim_review/llm_layer/templates/TRACK_A_INSTRUCTIONS.md`: supported syntax instructions.
- `docs/CODEX_WORKFLOW.md`: explain canonical numeric output requirement.

## Public Interfaces

```python
@dataclass(frozen=True, slots=True)
class NumericToken:
    text: str
    start: int
    end: int


class UnsupportedNumericSyntax(ValueError):
    pass


def scan_numeric_tokens(text: str) -> tuple[NumericToken, ...]:
    ...


def extract_numeric_tokens(text: str) -> tuple[str, ...]:
    return tuple(token.text for token in scan_numeric_tokens(text))


def reject_unsupported_numeric_syntax(
    text: str,
    tokens: tuple[NumericToken, ...],
) -> None:
    ...
```

Supported grammar:

```text
sign        := "+" | "-"
digit       := "0".."9"
plain_int   := digit+
grouped_int := digit{1,3} ("," digit{3})+
integer     := plain_int | grouped_int
fraction    := "." digit+
percent     := "%"
number      := sign? integer fraction? percent?
```

---

### Task 1: Define scanner behavior with a complete test matrix

**Files:**
- Create: `tests/unit/llm_layer/test_numeric_grammar.py`
- Create: `src/ansim_review/llm_layer/numeric_grammar.py`

**Interfaces:**
- Produces: `NumericToken`
- Produces: `scan_numeric_tokens(text) -> tuple[NumericToken, ...]`

- [ ] **Step 1: Write accepted-token tests**

```python
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("값은 0이다.", ("0",)),
        ("값은 -12이다.", ("-12",)),
        ("값은 +3이다.", ("+3",)),
        ("면적은 1,234이다.", ("1,234",)),
        ("비율은 12.50%이다.", ("12.50%",)),
        ("A는 10이고 B는 20이다.", ("10", "20")),
    ],
)
def test_scan_supported_tokens(text: str, expected: tuple[str, ...]) -> None:
    assert tuple(token.text for token in scan_numeric_tokens(text)) == expected
```

- [ ] **Step 2: Write span tests**

```python
def test_scanner_returns_original_spans() -> None:
    text = "접면 비율은 9.375%이다."
    token = scan_numeric_tokens(text)[0]
    assert text[token.start:token.end] == "9.375%"
```

- [ ] **Step 3: Run focused tests**

Run: `pytest tests/unit/llm_layer/test_numeric_grammar.py -v`

Expected: FAIL because the module does not exist.

- [ ] **Step 4: Implement a left-to-right scanner**

Implementation rules:

```text
1. A sign is consumed only when immediately followed by an ASCII digit.
2. A number may not begin inside an ASCII identifier character sequence.
3. Grouped and ungrouped integers are mutually exclusive parses.
4. A decimal point is consumed only when followed by one or more ASCII digits.
5. A percent sign is optional and terminates the token.
6. The token may not be followed by ASCII digit, letter, underscore, or dot.
```

Do not use `float()` or `Decimal()`; the scanner preserves text only.

- [ ] **Step 5: Run tests and commit**

```bash
pytest tests/unit/llm_layer/test_numeric_grammar.py -v
git add src/ansim_review/llm_layer/numeric_grammar.py tests/unit/llm_layer/test_numeric_grammar.py
git commit -m "feat: add canonical numeric token scanner"
```

### Task 2: Detect unsupported numeric-looking syntax

**Files:**
- Modify: `src/ansim_review/llm_layer/numeric_grammar.py`
- Modify: `tests/unit/llm_layer/test_numeric_grammar.py`

**Interfaces:**
- Produces: `reject_unsupported_numeric_syntax(text, tokens) -> None`

- [ ] **Step 1: Add failing rejection tests**

```python
@pytest.mark.parametrize(
    "text",
    [
        "값은 1e3이다.",
        "값은 1E-3이다.",
        "값은 .5이다.",
        "값은 1_000이다.",
        "값은 ½이다.",
        "값은 １２３이다.",
        "값은 12,34이다.",
        "값은 1,23,456이다.",
        "값은 10²이다.",
        "값은 ⑩이다.",
    ],
)
def test_unsupported_numeric_syntax_is_rejected(text: str) -> None:
    tokens = scan_numeric_tokens(text)
    with pytest.raises(UnsupportedNumericSyntax):
        reject_unsupported_numeric_syntax(text, tokens)
```

- [ ] **Step 2: Add nonnumeric identifier controls**

Accept text such as `R1`, `DOC-A`, and `RUN-ABC` when those sequences are identifiers rather than numeric claims. The scanner must not extract the `1` in `R1`.

- [ ] **Step 3: Run tests and confirm failures**

- [ ] **Step 4: Implement consumed-span masking**

Build a boolean list with one slot per code point and mark all accepted token spans. Inspect only unconsumed characters.

Reject when any of these conditions holds:

```python
character.isascii() and character.isdigit()
unicodedata.numeric(character) succeeds
re.search(r"(?<![A-Za-z0-9_])\.\d", remainder)
re.search(r"\d_[0-9]", remainder)
re.search(r"\d[eE][+-]?\d", remainder)
re.search(r"\d{1,3}(?:,\d+)+", remainder)
```

The implementation must report the first offending span deterministically:

```text
UNSUPPORTED_NUMERIC_SYNTAX at 4:7: 1e3
```

- [ ] **Step 5: Run tests and commit**

```bash
pytest tests/unit/llm_layer/test_numeric_grammar.py -v
git add src/ansim_review/llm_layer/numeric_grammar.py tests/unit/llm_layer/test_numeric_grammar.py
git commit -m "fix: reject unsupported numeric claim syntax"
```

### Task 3: Integrate scanner into Track A integrity validation

**Files:**
- Modify: `src/ansim_review/llm_layer/validators.py`
- Modify: `tests/unit/llm_layer/test_track_a_validator.py`

**Interfaces:**
- `extract_numeric_tokens()` remains import-compatible but delegates to `numeric_grammar`.
- `validate_track_a_integrity()` raises:
  - `UNSUPPORTED_NUMERIC_SYNTAX`
  - `NUMERIC_TOKEN_MISMATCH`
  - existing `unregistered numeric token`

- [ ] **Step 1: Add the empty-token bypass regression**

```python
@pytest.mark.parametrize("text", ["값은 1e3이다.", "값은 .5이다.", "값은 ½이다."])
def test_numeric_meaning_cannot_bypass_with_empty_declared_tokens(text: str) -> None:
    payload = _valid_output()
    payload["claims"][0]["text"] = text
    payload["claims"][0]["numeric_tokens"] = []
    validated = validate_track_a_output(payload, _bundle())
    with pytest.raises(ValueError, match="UNSUPPORTED_NUMERIC_SYNTAX"):
        validate_track_a_integrity(validated, _bundle())
```

- [ ] **Step 2: Add exact-declaration mismatch tests**

```text
text 9.375%, declared 9.375   -> mismatch
text 1,234, declared 1234     -> mismatch
text -12, declared 12         -> mismatch
```

- [ ] **Step 3: Run tests and confirm current bypass**

Run: `pytest tests/unit/llm_layer/test_track_a_validator.py -v`

- [ ] **Step 4: Replace regex extraction path**

For each claim:

```python
tokens = scan_numeric_tokens(claim.text)
reject_unsupported_numeric_syntax(claim.text, tokens)
extracted = tuple(token.text for token in tokens)
if extracted != claim.numeric_tokens:
    raise ValueError(f"NUMERIC_TOKEN_MISMATCH: {claim.claim_id}")
```

Then run the existing exact provenance loop unchanged.

- [ ] **Step 5: Run focused tests and commit**

```bash
pytest tests/unit/llm_layer/test_numeric_grammar.py tests/unit/llm_layer/test_track_a_validator.py -v
git add src/ansim_review/llm_layer/validators.py tests/unit/llm_layer/test_track_a_validator.py
git commit -m "fix: enforce complete Track A numeric declarations"
```

### Task 4: Verify source and calculation provenance behavior

**Files:**
- Modify: `tests/unit/llm_layer/test_track_a_validator.py`

**Interfaces:**
- No new production interface.

- [ ] **Step 1: Add evidence provenance cases**

Prove exact equality is required:

```text
claim 1,234 / evidence 1,234  -> pass
claim 1234 / evidence 1,234   -> reject
claim 0.5 / evidence .5       -> reject unless deterministic normalized evidence also contains 0.5
```

- [ ] **Step 2: Add calculation provenance cases**

Prove exact tokens from `inputs`, `substitution`, `raw_result`, `display_result`, and `comparison` remain available only for referenced successful calculations.

- [ ] **Step 3: Run tests and commit**

```bash
pytest tests/unit/llm_layer/test_track_a_validator.py -v
git add tests/unit/llm_layer/test_track_a_validator.py
git commit -m "test: cover numeric claim provenance"
```

### Task 5: Update Track A instructions and workflow documentation

**Files:**
- Modify: `src/ansim_review/llm_layer/templates/TRACK_A_INSTRUCTIONS.md`
- Modify: `docs/CODEX_WORKFLOW.md`
- Modify: `tests/unit/llm_layer/test_track_a_templates.py`

- [ ] **Step 1: Add failing template assertions**

Assert the template explicitly includes:

```text
canonical ASCII numeric tokens only
0.5 instead of .5
no exponent notation
no underscore separators
numeric_tokens must exactly match text order
```

- [ ] **Step 2: Update instructions**

Do not instruct Track A to convert values itself. State that unsupported source forms require a deterministic normalized source or calculation result.

- [ ] **Step 3: Run tests and commit**

```bash
pytest tests/unit/llm_layer/test_track_a_templates.py -v
git add src/ansim_review/llm_layer/templates/TRACK_A_INSTRUCTIONS.md docs/CODEX_WORKFLOW.md tests/unit/llm_layer/test_track_a_templates.py
git commit -m "docs: define Track A numeric grammar"
```

### Task 6: Full verification and issue closure

- [ ] **Step 1: Run focused suite**

```bash
pytest tests/unit/llm_layer -v
```

- [ ] **Step 2: Run full quality gate**

```bash
pytest -v
ruff check src tests
mypy src
python -m compileall -q src scripts web_runtime tests
```

- [ ] **Step 3: Mutation check**

Temporarily remove the unsupported-syntax call and confirm at least one of the new tests fails. Restore the code before committing.

- [ ] **Step 4: Commit verification corrections**

```bash
git add -A
git commit -m "test: verify Track A numeric grammar"
```

- [ ] **Step 5: PR body**

Use `Closes #25` only after all gates pass.