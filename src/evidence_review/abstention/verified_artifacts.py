"""One-read manifest verification for immutable finalizer JSON artifacts."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from evidence_review.filesystem_trust import verified_regular_file_below

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be an object")
    return cast(Mapping[str, object], value)


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _decode_json(raw_bytes: bytes, name: str) -> object:
    try:
        return json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid JSON artifact: {name}") from error


@dataclass(frozen=True, slots=True)
class VerifiedJsonArtifact:
    """Manifest-bound JSON content decoded from the exact bytes that were hashed."""

    name: str
    sha256: str
    raw_bytes: bytes
    document: object


@dataclass(frozen=True, slots=True)
class VerifiedRunSnapshot:
    """Immutable authority object for one verified set of run artifacts."""

    run_id: str
    artifacts: tuple[VerifiedJsonArtifact, ...]

    def _artifact(self, name: str) -> VerifiedJsonArtifact:
        for artifact in self.artifacts:
            if artifact.name == name:
                return artifact
        raise KeyError(name)

    def document(self, name: str) -> object:
        return self._artifact(name).document

    def raw_bytes(self, name: str) -> bytes:
        return self._artifact(name).raw_bytes


def verify_run_snapshot(
    run_directory: Path,
    *,
    required_artifacts: Sequence[str],
) -> VerifiedRunSnapshot:
    """Read, hash-verify, and decode every required artifact exactly once."""
    required = tuple(required_artifacts)
    if len(required) != len(set(required)):
        raise ValueError("required artifact names must be unique")
    for name in required:
        if not name or Path(name).name != name:
            raise ValueError(f"invalid artifact path: {name}")

    try:
        manifest_path = verified_regular_file_below(
            run_directory,
            ("run-manifest.json",),
            field="run manifest",
        )
        manifest_bytes = manifest_path.read_bytes()
    except (OSError, ValueError) as error:
        raise ValueError("invalid JSON artifact: run-manifest.json") from error
    manifest = _mapping(_decode_json(manifest_bytes, "run-manifest.json"), "run_manifest")
    unknown = sorted(set(manifest) - {"run_id", "artifacts"})
    if unknown:
        raise ValueError(f"run_manifest has unknown fields: {', '.join(unknown)}")
    run_id = _string(manifest.get("run_id"), "run_manifest.run_id")
    if run_directory.name != run_id:
        raise ValueError("run directory name does not match manifest run_id")
    artifact_hashes = _mapping(manifest.get("artifacts"), "run_manifest.artifacts")
    missing = sorted(set(required) - set(artifact_hashes))
    if missing:
        raise ValueError(f"run manifest is missing artifacts: {', '.join(missing)}")

    verified: list[VerifiedJsonArtifact] = []
    for name in required:
        expected = _string(
            artifact_hashes.get(name),
            f"run_manifest.artifacts.{name}",
        )
        if not _SHA256.fullmatch(expected):
            raise ValueError(f"invalid artifact hash: {name}")
        try:
            artifact_path = verified_regular_file_below(
                run_directory,
                (name,),
                field=f"run artifact {name}",
            )
            raw_bytes = artifact_path.read_bytes()
        except (OSError, ValueError) as error:
            raise ValueError(f"missing artifact: {name}") from error
        actual = hashlib.sha256(raw_bytes).hexdigest()
        if actual != expected:
            raise ValueError(f"artifact hash mismatch: {name}")
        document = _decode_json(raw_bytes, name)
        verified.append(
            VerifiedJsonArtifact(
                name=name,
                sha256=actual,
                raw_bytes=raw_bytes,
                document=document,
            )
        )

    return VerifiedRunSnapshot(run_id=run_id, artifacts=tuple(verified))
