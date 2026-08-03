from __future__ import annotations

from pathlib import Path

from ansim_review.parser_reproducibility.normalization import (
    normalize_json_artifact,
    normalize_markdown_artifact,
)
from tests.unit.parser_reproducibility._helpers import config


def test_only_approved_metadata_is_replaced(tmp_path: Path) -> None:
    run_root = tmp_path / "run-a"
    payload = {
        "metadata": {
            "parsed_at": "2026-08-03T00:00:00Z",
            "output_directory": str(run_root),
            "title": "Title",
        },
        "kids": [
            {
                "content": "A  B",
                "bounding box": [1, 2, 3, 4],
            }
        ],
    }
    result = normalize_json_artifact(payload, config(), run_root)

    assert isinstance(result.value, dict)
    metadata = result.value["metadata"]
    assert isinstance(metadata, dict)
    assert metadata["parsed_at"] == "<NONDETERMINISTIC>"
    assert metadata["output_directory"] == "<RUN_ROOT>"
    assert metadata["title"] == "Title"
    kids = result.value["kids"]
    assert isinstance(kids, list)
    assert isinstance(kids[0], dict)
    assert kids[0]["content"] == "A  B"
    assert kids[0]["bounding box"] == [1, 2, 3, 4]
    assert payload["metadata"]["parsed_at"] == "2026-08-03T00:00:00Z"


def test_markdown_normalization_is_bounded(tmp_path: Path) -> None:
    run_root = tmp_path / "run-a"
    raw = (
        b"\xef\xbb\xbf# Title\r\n\r\n"
        + str(run_root).encode("utf-8")
        + b"\\images\\a.png  \r\n"
    )
    result = normalize_markdown_artifact(raw, run_root)

    assert result.text == "# Title\n\n<RUN_ROOT>/images\\a.png  \n"
    assert result.text.endswith("  \n")
    assert "# Title\n\n" in result.text


def test_content_whitespace_remains_meaningful(tmp_path: Path) -> None:
    one = normalize_markdown_artifact(b"A  B\n", tmp_path)
    two = normalize_markdown_artifact(b"A B\n", tmp_path)
    assert one.sha256 != two.sha256
