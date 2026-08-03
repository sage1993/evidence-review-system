from __future__ import annotations

import json
from pathlib import Path

import pytest

from ansim_review.parser_reproducibility.report import (
    validate_opendataloader_reproducibility,
)
from tests.unit.parser_reproducibility._helpers import config, write_pdf, write_run


def add_table(run: Path) -> None:
    path = run / "document.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["pages"][0]["kids"].append(
        {
            "type": "table",
            "page number": 1,
            "bounding box": [50, 60, 300, 200],
            "rows": [
                {
                    "cells": [
                        {"content": "Header A"},
                        {"content": "Header B"},
                    ]
                },
                {
                    "cells": [
                        {"content": "Value A"},
                        {"content": "Value B"},
                    ]
                },
            ],
        }
    )
    path.write_text(
        json.dumps(document, separators=(",", ":")),
        encoding="utf-8",
    )


@pytest.mark.parametrize("fixture_kind", ["text", "table", "warning"])
def test_realistic_fixture_matrix_is_reproducible(
    tmp_path: Path,
    fixture_kind: str,
) -> None:
    source = write_pdf(tmp_path / f"{fixture_kind}.pdf")
    warning = "page 1: inspect layout" if fixture_kind == "warning" else None
    run_a = write_run(tmp_path / "run-a", source, warning=warning)
    run_b = write_run(tmp_path / "run-b", source, warning=warning)
    if fixture_kind == "table":
        add_table(run_a)
        add_table(run_b)

    first = validate_opendataloader_reproducibility(
        source,
        run_a,
        run_b,
        config(),
    )
    second = validate_opendataloader_reproducibility(
        source,
        run_a,
        run_b,
        config(),
    )

    assert first.status == "SEMANTICALLY_IDENTICAL"
    assert first == second
    if fixture_kind == "warning":
        assert first.warning_count == 1
