"""Active approved-rule manifest loading and hash verification."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from ansim_review.rule_engine.loader import load_rule
from ansim_review.rule_engine.schema import RuleSpec


def sha256_file(path: Path) -> str:
    """Return a lowercase SHA-256 digest for one file."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object")
    return cast(Mapping[str, object], value)


def _sequence(value: object, field: str) -> Sequence[object]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise ValueError(f"{field} must be an array")
    return cast(Sequence[object], value)


def load_active_rules(project_root: Path, manifest_path: Path) -> tuple[RuleSpec, ...]:
    """Load only hash-verified approved rules declared by the active manifest."""
    if not manifest_path.is_file():
        return ()
    payload = _mapping(json.loads(manifest_path.read_text(encoding="utf-8")), "manifest")
    entries = _sequence(payload.get("rules", []), "manifest.rules")
    rules: list[RuleSpec] = []
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(entries):
        entry = _mapping(item, f"manifest.rules[{index}]")
        rule_id = entry.get("rule_id")
        version = entry.get("version")
        relative_path = entry.get("path")
        expected_hash = entry.get("sha256")
        required_values = (rule_id, version, relative_path, expected_hash)
        if not all(isinstance(value, str) and value for value in required_values):
            raise ValueError("manifest rule entry requires rule_id, version, path, and sha256")
        key = cast(tuple[str, str], (rule_id, version))
        if key in seen:
            raise ValueError(f"duplicate active rule: {rule_id}@{version}")
        seen.add(key)
        path = (project_root / cast(str, relative_path)).resolve()
        approved_root = (project_root / "rules" / "approved").resolve()
        if path.parent != approved_root or not path.is_file():
            raise ValueError(f"approved rule path is invalid: {relative_path}")
        if sha256_file(path) != expected_hash:
            raise ValueError(f"approved rule hash mismatch: {rule_id}@{version}")
        rule = load_rule(json.loads(path.read_text(encoding="utf-8")))
        if rule.rule_id != rule_id or rule.version != version:
            raise ValueError(f"approved rule identity mismatch: {rule_id}@{version}")
        rules.append(rule)
    return tuple(sorted(rules, key=lambda rule: (rule.rule_id, rule.version)))
