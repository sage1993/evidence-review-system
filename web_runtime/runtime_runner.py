"""Execute one deterministic golden case in an extracted web runtime."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ansim_review.canonical_json import dump_bytes
from ansim_review.golden_cases import run_golden_case

ROOT = Path(__file__).resolve().parent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--path-hint", default="")
    arguments = parser.parse_args()
    cases = json.loads(
        (ROOT / "examples/golden-cases.json").read_text(encoding="utf-8")
    )
    case = next(
        (item for item in cases if item["case_id"] == arguments.case_id),
        None,
    )
    if case is None:
        raise SystemExit("unknown case")
    sys.stdout.buffer.write(dump_bytes(run_golden_case(case)))


if __name__ == "__main__":
    main()
