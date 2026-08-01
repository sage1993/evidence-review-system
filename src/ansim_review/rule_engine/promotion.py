"""Human-attributed promotion of immutable candidate rules."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, cast

from ansim_review.canonical_json import dumps
from ansim_review.contracts.identifiers import safe_direct_child
from ansim_review.rule_engine.loader import load_rule
from ansim_review.rule_engine.manifest import sha256_file


def _read_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"rules": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("rules"), list):
        raise ValueError("active rule manifest is invalid")
    return cast(dict[str, Any], payload)


def _project_root(manifest_path: Path) -> Path:
    if manifest_path.parent.name != "manifests" or manifest_path.parent.parent.name != "rules":
        raise ValueError("manifest path must be rules/manifests/active.json")
    return manifest_path.parent.parent.parent


def promote_candidate(
    candidate_path: Path,
    approved_dir: Path,
    manifest_path: Path,
    *,
    reviewer_id: str,
    review_date: str,
) -> Path:
    """Create an approved copy and update the active manifest deterministically."""
    if not reviewer_id.strip():
        raise ValueError("reviewer identity is required")
    if not review_date.strip():
        raise ValueError("review date is required")
    try:
        date.fromisoformat(review_date)
    except ValueError as error:
        raise ValueError("review date must use ISO YYYY-MM-DD") from error
    if not candidate_path.is_file():
        raise ValueError("candidate rule does not exist")
    candidate_bytes = candidate_path.read_bytes()
    payload = json.loads(candidate_bytes.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("candidate rule must be an object")
    rule = load_rule(payload)
    approved_path = safe_direct_child(
        approved_dir,
        f"{rule.rule_id}@{rule.version}.json",
        "approved_rule_path",
    )
    project_root = _project_root(manifest_path)
    candidate_hash = sha256_file(candidate_path)
    approved_payload = dict(payload)
    approved_payload["approval"] = {
        "reviewer_id": reviewer_id.strip(),
        "review_date": review_date,
        "candidate_sha256": candidate_hash,
    }
    approved_text = dumps(approved_payload) + "\n"
    if approved_path.exists() and approved_path.read_text(encoding="utf-8") != approved_text:
        raise FileExistsError(
            f"approved rule already exists with different bytes: {approved_path.name}"
        )
    approved_path.parent.mkdir(parents=True, exist_ok=True)
    approved_path.write_text(approved_text, encoding="utf-8", newline="\n")
    approved_hash = sha256_file(approved_path)
    relative_path = approved_path.relative_to(project_root.resolve()).as_posix()
    manifest = _read_manifest(manifest_path)
    entries = [
        entry
        for entry in cast(list[dict[str, Any]], manifest["rules"])
        if not (entry.get("rule_id") == rule.rule_id and entry.get("version") == rule.version)
    ]
    entries.append(
        {
            "rule_id": rule.rule_id,
            "version": rule.version,
            "path": relative_path,
            "sha256": approved_hash,
            "reviewer_id": reviewer_id.strip(),
            "review_date": review_date,
            "candidate_sha256": candidate_hash,
        }
    )
    entries.sort(key=lambda entry: (str(entry["rule_id"]), str(entry["version"])))
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(dumps({"rules": entries}) + "\n", encoding="utf-8", newline="\n")
    return approved_path
