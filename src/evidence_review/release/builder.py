"""Build deterministic evidence-review release candidates behind explicit gates."""
from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from evidence_review.canonical_json import dump_bytes, sha256_json
from evidence_review.contracts.formats import RELEASE_FORMAT
from evidence_review.packaging.codex_bundle import build_codex_bundle
from evidence_review.packaging.web_bundle import build_web_runtime_zip
from evidence_review.release.attestation import (
    PROCESS_ATTESTATION,
    HumanAttestation,
    attestation_document,
    validate_attestation,
    write_attestation,
)
from evidence_review.release.config import (
    DEFAULT_RELEASE_CONFIG,
    ReleaseConfig,
    resolve_attestation_record,
    resolve_evidence_database,
)
from evidence_review.release.output_verifier import validate_release_output
from evidence_review.release.validator import (
    validate_release_workspace,
    verify_release_packet,
)

_FIXED_TIME = (1980, 1, 1, 0, 0, 0)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _zip_directory(source: Path, output: Path) -> None:
    with zipfile.ZipFile(
        output,
        "x",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for path in sorted(item for item in source.rglob("*") if item.is_file()):
            info = zipfile.ZipInfo(path.relative_to(source).as_posix(), _FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            info.create_system = 3
            archive.writestr(
                info,
                path.read_bytes(),
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            )


def _artifact_entries(output: Path) -> list[dict[str, object]]:
    names = (
        "evidence.sqlite",
        "approved-rules.zip",
        "codex-workspace.zip",
        "chatgpt-web-runtime.zip",
        "release-validation.json",
        "final-review-packet.json",
    )
    return [
        {
            "path": name,
            "sha256": _sha(output / name),
            "size": (output / name).stat().st_size,
        }
        for name in names
    ]


def _automated_reason_codes(
    workspace_validation: Mapping[str, object],
    output_validation: Mapping[str, object],
) -> list[str]:
    """Return stable independent release-gate reasons in policy order."""
    reasons: list[str] = []
    if workspace_validation.get("status") != "PASS":
        reasons.append("AUTOMATED_VALIDATION_FAILED")
    workspace_errors = workspace_validation.get("errors", [])
    if (
        isinstance(workspace_errors, list)
        and "DOCUMENTATION_INTEGRITY_FAILED" in workspace_errors
    ):
        reasons.append("DOCUMENTATION_INTEGRITY_FAILED")
    if output_validation.get("status") != "PASS":
        reasons.append("RELEASE_OUTPUT_VALIDATION_FAILED")
    return reasons


def _combined_validation_report(
    workspace_validation: dict[str, object],
    output_validation: dict[str, object],
) -> dict[str, object]:
    """Embed final-output verification without changing the report contract."""
    errors = list(cast(list[str], workspace_validation.get("errors", [])))
    if output_validation.get("status") != "PASS":
        errors.append("RELEASE_OUTPUT_VALIDATION_FAILED")
    return {
        **workspace_validation,
        "status": (
            "PASS"
            if workspace_validation.get("status") == "PASS"
            and output_validation.get("status") == "PASS"
            else "FAIL"
        ),
        "errors": errors,
        "release_output": output_validation,
    }


@dataclass(frozen=True, slots=True)
class ReleaseInputs:
    """Read-only inputs validated before a release stage is created."""

    evidence: Path
    run_id: str
    packet_bytes: bytes
    packet_hash: str


def _preflight_release(
    workspace_root: Path,
    output_directory: Path,
    config: ReleaseConfig,
    run_id: str | None,
) -> ReleaseInputs:
    if output_directory.exists():
        raise FileExistsError(output_directory)
    evidence = resolve_evidence_database(workspace_root, config)
    if not evidence.is_file():
        raise FileNotFoundError(evidence)
    selected_packet = verify_release_packet(workspace_root, run_id)
    return ReleaseInputs(
        evidence=evidence,
        run_id=selected_packet.run_id,
        packet_bytes=selected_packet.raw_bytes,
        packet_hash=selected_packet.packet_hash,
    )


def _publish_stage(stage: Path, output_directory: Path) -> None:
    """Publish one completed stage without replacing an existing output."""
    parent = output_directory.parent.resolve()
    lock_path = parent / f".{output_directory.name}.publish.lock"
    try:
        descriptor = os.open(
            lock_path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        os.close(descriptor)
    except FileExistsError as error:
        raise FileExistsError(output_directory) from error
    try:
        if output_directory.exists():
            raise FileExistsError(output_directory)
        os.replace(stage, output_directory)
    finally:
        lock_path.unlink(missing_ok=True)


def build_evidence_release(
    workspace_root: Path,
    output_directory: Path,
    *,
    run_id: str | None = None,
    config: ReleaseConfig = DEFAULT_RELEASE_CONFIG,
) -> dict[str, object]:
    """Build and atomically publish a deterministic evidence release."""
    workspace_root = workspace_root.resolve()
    output_directory = output_directory.resolve(strict=False)
    inputs = _preflight_release(
        workspace_root,
        output_directory,
        config,
        run_id,
    )
    output_parent = output_directory.parent
    output_parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        dir=output_parent,
        prefix=f".{output_directory.name}.stage-",
    ) as temporary:
        stage = Path(temporary) / "release"
        stage.mkdir()
        shutil.copyfile(inputs.evidence, stage / "evidence.sqlite")
        packet_output = stage / "final-review-packet.json"
        packet_output.write_bytes(inputs.packet_bytes)
        if _sha(packet_output) != inputs.packet_hash:
            raise ValueError("release staged packet hash does not match selected packet")

        with tempfile.TemporaryDirectory(
            prefix="evidence-review-release-build-"
        ) as temporary_build:
            build_root = Path(temporary_build)
            codex = build_root / "codex-workspace"
            build_codex_bundle(workspace_root, codex)
            _zip_directory(codex, stage / "codex-workspace.zip")
            _zip_directory(
                workspace_root / "rules" / "approved",
                stage / "approved-rules.zip",
            )
        build_web_runtime_zip(
            workspace_root,
            stage / "chatgpt-web-runtime.zip",
        )

        workspace_validation = validate_release_workspace(
            workspace_root,
            run_id=inputs.run_id,
        )
        output_validation = validate_release_output(stage)
        validation = _combined_validation_report(
            workspace_validation,
            output_validation,
        )
        (stage / "release-validation.json").write_bytes(
            dump_bytes(validation)
        )

        artifacts = _artifact_entries(stage)
        candidate_hash = sha256_json(artifacts)
        packet_hash = inputs.packet_hash
        reasons = _automated_reason_codes(
            workspace_validation,
            output_validation,
        )

        attestation_path = resolve_attestation_record(workspace_root, config)
        attestation: HumanAttestation | None = None
        if not attestation_path.is_file():
            reasons.append("PROCESS_ATTESTATION_MISSING")
        else:
            try:
                attestation = validate_attestation(
                    attestation_path,
                    expected_candidate_hash=candidate_hash,
                    expected_packet_hash=packet_hash,
                    expected_reviewer_id=config.expected_reviewer_id,
                )
            except (OSError, ValueError):
                reasons.append("PROCESS_ATTESTATION_INVALID")

        status = "RELEASE_READY" if not reasons else "BLOCKED"
        if attestation is not None and status == "RELEASE_READY":
            write_attestation(
                stage / config.attestation_record_name,
                attestation,
            )
        manifest = {
            "format": RELEASE_FORMAT,
            "version": 1,
            "release": config.release_id,
            "run_id": inputs.run_id,
            "status": status,
            "reason_codes": reasons,
            "candidate_hash": candidate_hash,
            "packet_hash": packet_hash,
            "artifacts": artifacts,
            "attestation_assurance": PROCESS_ATTESTATION,
            "cryptographic_identity_verified": False,
            "expected_reviewer_id": config.expected_reviewer_id,
            "attestation": (
                None if attestation is None else attestation_document(attestation)
            ),
            "tag_allowed": status == "RELEASE_READY",
        }
        (stage / "release-manifest.json").write_bytes(
            dump_bytes(manifest)
        )
        _publish_stage(stage, output_directory)
    return manifest

def build_ansim_release(
    workspace_root: Path,
    output_directory: Path,
    *,
    run_id: str | None = None,
) -> dict[str, object]:
    """Compatibility wrapper for the original public Python function name."""
    return build_evidence_release(
        workspace_root,
        output_directory,
        run_id=run_id,
    )
