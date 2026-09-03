from __future__ import annotations

import json

import pytest

from evidence_review.review_packet.reference_projection import (
    project_reference_record,
)


@pytest.mark.parametrize(
    ("evidence_type", "element_type", "visual_kind", "expected_type"),
    [
        ("clause", None, None, "TEXT"),
        ("table", None, None, "TABLE"),
        ("pdf_page", None, None, "PDF_PAGE"),
        ("visual", None, None, "IMAGE"),
        ("visual", None, "composite_diagram", "DIAGRAM"),
        ("visual", None, "site_drawing", "DRAWING"),
    ],
)
def test_reference_projection_classifies_allowlisted_types(
    evidence_type: str,
    element_type: str | None,
    visual_kind: str | None,
    expected_type: str,
) -> None:
    projected = project_reference_record(
        evidence_type=evidence_type,
        element_type=element_type,
        element_raw_json=None,
        table_raw_json=None,
        visual_kind=visual_kind,
    )

    assert projected["type"] == expected_type


def test_table_projection_exposes_only_bounded_semantic_cells() -> None:
    raw = json.dumps(
        {
            "cells": [
                {
                    "row": 0,
                    "column": 0,
                    "text": "기준",
                    "row_span": 1,
                    "column_span": 1,
                    "selected": False,
                    "raw_internal_id": "do-not-project",
                },
                {
                    "row": 1,
                    "column": 0,
                    "text": "3.0m 이상",
                    "row_span": 1,
                    "column_span": 1,
                    "selected": True,
                },
            ],
            "database_debug": {"reasoning": "hidden"},
        }
    )

    projected = project_reference_record(
        evidence_type="table",
        element_type=None,
        element_raw_json=None,
        table_raw_json=raw,
        visual_kind=None,
    )

    assert projected == {
        "type": "TABLE",
        "table": {
            "cells": [
                {
                    "row": 0,
                    "column": 0,
                    "text": "기준",
                    "row_span": 1,
                    "column_span": 1,
                    "selected": False,
                },
                {
                    "row": 1,
                    "column": 0,
                    "text": "3.0m 이상",
                    "row_span": 1,
                    "column_span": 1,
                    "selected": True,
                },
            ]
        },
        "visual": None,
    }


def test_table_projection_rejects_unbounded_cell_count() -> None:
    raw = json.dumps(
        {
            "cells": [
                {"row": index, "column": 0, "text": "cell"}
                for index in range(201)
            ]
        }
    )

    projected = project_reference_record(
        evidence_type="table",
        element_type=None,
        element_raw_json=None,
        table_raw_json=raw,
        visual_kind=None,
    )

    assert projected == {"type": "TABLE", "table": None, "visual": None}
