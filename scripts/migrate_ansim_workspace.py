#!/usr/bin/env python3
"""Inventory and back up an external Ansim Housing workspace."""
from __future__ import annotations

import argparse
from pathlib import Path

from ansim_review.migration.ansim_workspace import inventory_and_backup


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("workspace", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--date", required=True)
    arguments = parser.parse_args()
    inventory_and_backup(arguments.workspace, arguments.output, date_label=arguments.date)
    print("ANSIM_INVENTORY_COMPLETE")


if __name__ == "__main__":
    main()
