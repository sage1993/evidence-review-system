"""Build deterministic evidence-review release candidates behind explicit gates."""
from __future__ import annotations

import hashlib
import shutil
import tempfile
import zipfile
from pathlib import Path

from ansim_review.canonical_json import dump_bytes, sha256_json
from ansim_review.contracts.formats import RELEASE_FORMAT
from ansim_review.packaging.codex_bundle import build_codex_bundle
from ansim_review.packaging.web_bundle import build_web_runtime_zip
from ansim_review.release.attestation import (
    PROCESS_ATTESTATION,
    HumanAttestation,
    attestation_document,
    validate_attestation,
    write_attestation,
)
from ansim_review.release.config import (
    DEFAULT_RELEASE_CONFIG,
    ReleaseConfig,
    resolve_attestation_record,
    resolve_evidence_database,
)
from ansim_review.release.validator import validate_release_workspace

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


def build_evidence_release(
    workspace_root: Path,
    output_directory: Path,
    *,
    config: ReleaseConfig = DEFAULT_RELEASE_CONFIG,
) -> dict[str, object]:
    """Build release artifacts and require exact named process attestation."""
    if output_directory.exists():
        raise FileExistsError(output_directory)
    output_directory.mkdir(parents=True)

    evidence = resolve_evidence_database(workspace_root, config)
    packet = workspace_root / "runs" / "final-review-packet.json"
    if not evidence.is_file():
        raise FileNotFoundError(evidence)
    if not packet.is_file():
        raise FileNotFoundError(packet)
    shutil.copyfile(evidence, output_directory / "evidence.sqlite")
    shutil.copyfile(packet, output_directory / "final-review-packet.json")

    with tempfile.TemporaryDirectory(prefix="evidence-review-release-build-") as temporary:
        temp = Path(temporary)
        codex = temp / "codex-workspace"
        build_codex_bundle(workspace_root, codex)
        _zip_directory(codex, output_directory / "codex-workspace.zip")
        _zip_directory(
            workspace_root / "rules" / "approved",
            output_directory / "approved-rules.zip",
        )
    build_web_runtime_zip(
        workspace_root,
        output_directory / "chatgpt-web-runtime.zip",
    )
    validation = validate_release_workspace(
        workspace_root,
        output_directory / "release-validation.json",
    )
    artifacts = _artifact_entries(output_directory)
    candidate_hash = sha256_json(artifacts)
    packet_hash = _sha(output_directory / "final-review-packet.json")
    reasons: list[str] = []
    if validation["status"] != "PASS":
        reasons.append("AUTOMATED_VALIDATION_FAILED")

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
            output_directory / config.attestation_record_name,
            attestation,
        )
    manifest = {
        "format": RELEASE_FORMAT,
        "version": 1,
        "release": config.release_id,
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
    (output_directory / "release-manifest.json").write_bytes(
        dump_bytes(manifest)
    )
    return manifest


def build_ansim_release(
    workspace_root: Path,
    output_directory: Path,
) -> dict[str, object]:
    """Compatibility wrapper for the original public Python function name."""
    return build_evidence_release(workspace_root, output_directory)
