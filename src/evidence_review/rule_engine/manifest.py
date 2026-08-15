"""Runtime loading for strictly governed active-rule manifests."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from evidence_review.rule_engine.governance_contract import (
    RuleSelectionContext,
    RuleSelectionResult,
    active_rule_manifest_bytes,
    load_active_rule_manifest_bytes,
)
from evidence_review.rule_engine.governance_verify import (
    GovernanceVerificationError,
    verify_manifest_entry,
)
from evidence_review.rule_engine.schema import RuleSpec
from evidence_review.rule_engine.selection import select_active_rules


@dataclass(frozen=True, slots=True)
class GovernedRuleLoad:
    """Runtime rules paired with their explicit selection authority."""

    rules: tuple[RuleSpec, ...]
    selection: RuleSelectionResult


def sha256_file(path: Path) -> str:
    """Return a lowercase SHA-256 digest for one file."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _blocked(
    context: RuleSelectionContext,
    reasons: tuple[str, ...],
    manifest_sha256: str | None = None,
) -> GovernedRuleLoad:
    return GovernedRuleLoad(
        rules=(),
        selection=RuleSelectionResult(
            status="BLOCKED",
            context=context,
            manifest_sha256=manifest_sha256,
            selected_rules=(),
            excluded_rules=(),
            reasons=reasons,
        ),
    )


def _safe_relative_path(path: Path) -> Path:
    text = path.as_posix()
    pure = PurePosixPath(text)
    if (
        path.is_absolute()
        or "\\" in text
        or ":" in text
        or text in {"", ".", ".."}
        or pure.as_posix() != text
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        raise ValueError("active manifest must be a repository-relative POSIX path")
    return Path(*pure.parts)


def _resolve_manifest(project_root: Path, manifest_path: Path) -> tuple[Path, Path]:
    root = project_root.resolve(strict=True)
    if project_root.is_symlink() or not root.is_dir():
        raise ValueError("project_root must be a real directory")
    if manifest_path.is_absolute():
        try:
            relative = _safe_relative_path(manifest_path.relative_to(root))
        except ValueError as error:
            raise ValueError("active manifest must be below project_root") from error
    else:
        relative = _safe_relative_path(manifest_path)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("active manifest path traverses a symlink")
    return root, current


def _duplicate_free_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _is_legacy_manifest(data: bytes) -> bool:
    try:
        text = data.decode("utf-8")
        value: object = json.loads(text, object_pairs_hook=_duplicate_free_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return False
    return (
        isinstance(value, dict)
        and "rules" in value
        and "format" not in value
        and "version" not in value
    )


def _manifest_error_code(error: ValueError) -> str:
    message = str(error)
    if "duplicate active rule_id" in message:
        return "DUPLICATE_ACTIVE_RULE_ID"
    if "repository-relative POSIX path" in message:
        return "UNSAFE_ARTIFACT_PATH"
    return "ACTIVE_MANIFEST_INVALID"


def load_governed_active_rules(
    project_root: Path,
    manifest_path: Path,
    context: RuleSelectionContext,
) -> GovernedRuleLoad:
    """Verify complete runtime authority, then load only exact-scope rules."""
    try:
        root, manifest_file = _resolve_manifest(project_root, manifest_path)
    except (OSError, ValueError):
        return _blocked(context, ("INVALID_ACTIVE_RULE_MANIFEST_PATH",))
    if not manifest_file.is_file():
        return _blocked(context, ("ACTIVE_RULE_MANIFEST_MISSING",))

    manifest_bytes = manifest_file.read_bytes()
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    try:
        manifest = load_active_rule_manifest_bytes(manifest_bytes)
    except ValueError as error:
        reason = (
            "RULE_GOVERNANCE_LEGACY_MANIFEST"
            if _is_legacy_manifest(manifest_bytes)
            else _manifest_error_code(error)
        )
        return _blocked(context, (reason,), manifest_sha256)
    if active_rule_manifest_bytes(manifest) != manifest_bytes:
        return _blocked(context, ("ACTIVE_MANIFEST_INVALID",), manifest_sha256)

    verified_by_identity: dict[tuple[str, str], RuleSpec] = {}
    reasons: list[str] = []
    for entry in manifest.rules:
        try:
            verified = verify_manifest_entry(root, entry, mode="RUNTIME")
        except GovernanceVerificationError as error:
            reasons.append(error.code)
        else:
            verified_by_identity[(entry.rule_id, entry.rule_version)] = verified.rule
    if reasons:
        return _blocked(context, tuple(sorted(set(reasons))), manifest_sha256)

    selection = select_active_rules(manifest.rules, context, manifest_sha256)
    if selection.status != "SELECTED":
        return GovernedRuleLoad(rules=(), selection=selection)
    rules = tuple(
        verified_by_identity[(item.rule_id, item.rule_version)]
        for item in selection.selected_rules
    )
    return GovernedRuleLoad(rules=rules, selection=selection)


def load_active_rules(project_root: Path, manifest_path: Path) -> tuple[RuleSpec, ...]:
    """Reject the legacy no-context runtime authority path."""
    del project_root, manifest_path
    raise ValueError("explicit RuleSelectionContext is required")
