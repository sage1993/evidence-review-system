from __future__ import annotations

import importlib
import json


def _project_reference_record(**overrides: str | None) -> dict[str, object]:
    module = importlib.import_module(
        "evidence_review.review_packet.reference_projection"
    )
    values: dict[str, str | None] = {
        "evidence_type": "clause",
        "element_type": None,
        "element_raw_json": None,
        "table_raw_json": None,
        "visual_kind": None,
    }
    values.update(overrides)
    return module.project_reference_record(**values)


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

    projected = _project_reference_record(
        evidence_type="table",
        table_raw_json=raw,
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


def test_visual_projection_maps_parser_kind_without_raw_path_or_id() -> None:
    projected = _project_reference_record(
        evidence_type="visual",
        visual_kind="composite_diagram",
    )

    assert projected == {
        "type": "DIAGRAM",
        "table": None,
        "visual": {"kind": "composite_diagram"},
    }


def test_malformed_table_structure_falls_back_to_page_bbox() -> None:
    projected = _project_reference_record(
        evidence_type="table",
        table_raw_json=json.dumps(
            {"cells": [{"row": -1, "column": 0, "text": "invalid"}]}
        ),
    )

    assert projected == {
        "type": "TABLE", "table": None, "visual": None
    }
