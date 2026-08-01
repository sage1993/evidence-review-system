from pathlib import Path

TEMPLATE = Path("src/ansim_review/llm_layer/templates/track-a.md")
GRAMMAR_DOC = Path("docs/TRACK_A_NUMERIC_GRAMMAR.md")


def test_track_a_template_declares_exact_numeric_grammar() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")

    for required in (
        "numeric_tokens",
        "canonical ASCII",
        "1e3",
        ".5",
        "1_000",
        "12,34",
        "Unicode",
        "0.5",
    ):
        assert required in text


def test_numeric_grammar_document_lists_supported_and_rejected_forms() -> None:
    text = GRAMMAR_DOC.read_text(encoding="utf-8")

    for required in (
        "0",
        "-12",
        "+3",
        "1,234",
        "12.50%",
        "1e3",
        ".5",
        "1_000",
        "½",
        "１２３",
        "NUMERIC_TOKEN_MISMATCH",
        "UNSUPPORTED_NUMERIC_SYNTAX",
    ):
        assert required in text
