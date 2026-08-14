#!/usr/bin/env python3
"""Build a gated Evidence Review System release candidate."""
from __future__ import annotations

import argparse
from pathlib import Path

from ansim_review.release.builder import build_evidence_release


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace", type=Path)
    parser.add_argument("output", type=Path)
    arguments = parser.parse_args()
    manifest = build_evidence_release(arguments.workspace, arguments.output)
    print(manifest["status"])
    if manifest["status"] != "RELEASE_READY":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
