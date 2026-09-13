import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import zipfile
from pathlib import Path
from types import TracebackType

import pytest
from helpers.rule_governance import build_valid_governance_tree

from evidence_review.canonical_json import dump_bytes
from evidence_review.evidence.store import EvidenceStore
from evidence_review.release.attestation import REQUIRED_CHECK_IDS
from evidence_review.release.builder import build_ansim_release, build_evidence_release
from evidence_review.release.config import ReleaseConfig
from evidence_review.release.validator import validate_release_workspace

from ._fixtures import write_valid_finalized_run


def _workspace(
    root: Path,
    *,
    packet_snapshot_sha256: str | None = None,
) -> str:
    repository_root = Path(__file__).parents[3]
    shutil.copytree(
        repository_root / "src/evidence_review",
        root / "src/evidence_review",
    )
    shutil.copytree(
        repository_root / "src/ansim_review",
        root / "src/ansim_review",
    )
    build_valid_governance_tree(root)
    (root / "formulas").mkdir()
    (root / "formulas/manifest.json").write_text("{}", encoding="utf-8")
    (root / "examples").mkdir()
    (root / "examples/sample-request.json").write_text("{}", encoding="utf-8")
    shutil.copytree(repository_root / "web_runtime", root / "web_runtime")
    (root / "tests/golden/questions").mkdir(parents=True)
    shutil.copy2(
        repository_root / "tests/golden/questions/ansim_cases.json",
        root / "tests/golden/questions/ansim_cases.json",
    )
    for name in ("ers-pdf", "ers-review"):
        shutil.copytree(
            repository_root / "skills" / name,
            root / "skills" / name,
        )
    (root / "README.md").write_text("# Release fixture\n", encoding="utf-8")
    (root / "AGENTS.md").write_text("# agents\n", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs/OFFLINE_EXECUTION.md").write_text(
        "# Offline Execution\n",
        encoding="utf-8",
    )
    (root / "documentation-integrity.json").write_text(
        json.dumps(
            {
                "format": "evidence-review/documentation-integrity-config",
                "version": 1,
                "current_roots": [
                    "README.md",
                    "AGENTS.md",
                    "docs/OFFLINE_EXECUTION.md",
                    "skills",
                ],
                "historical_roots": [],
                "current_overrides": [],
                "historical_overrides": [],
                "generated_documents": [],
            }
        ),
        encoding="utf-8",
    )
    return write_valid_finalized_run(
        root,
        packet_snapshot_sha256=packet_snapshot_sha256,
    )


def _attestation(
    candidate_hash: str,
    packet_hash: str,
    *,
    reviewer_id: str = "reviewer@example.com",
) -> dict[str, object]:
    return {
        "format": "evidence-review/human-attestation",
        "version": 1,
        "assurance_level": "PROCESS_ATTESTATION",
        "reviewer_id": reviewer_id,
        "reviewed_at": "2026-08-02T14:00:00+09:00",
        "attestation": "REVIEWED_AND_ACCEPTED_FOR_RELEASE",
        "release_candidate_hash": candidate_hash,
        "packet_hash": packet_hash,
        "checks": [
            {
                "check_id": item,
                "status": "PASS",
                "evidence": f"evidence/{item}",
            }
            for item in REQUIRED_CHECK_IDS
        ],
    }


def _legacy_acceptance(candidate_hash: str, packet_hash: str) -> dict[str, object]:
    return {
        "format": "ansim/human-acceptance",
        "version": 1,
        "reviewer_id": "reviewer@example.com",
        "reviewed_at": "2026-08-02T14:00:00+09:00",
        "signature": "reviewer@example.com:approved",
        "release_candidate_hash": candidate_hash,
        "packet_hash": packet_hash,
        "checks": [],
    }


def _bind_database_hash_to_run(root: Path, run_id: str, digest: str) -> None:
    run_directory = root / "runs" / run_id
    bundle_path = run_directory / "track-a-bundle.json"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    provenance = bundle["inputs"]["evidence_snapshot_provenance"]
    provenance["evidence_db_sha256"] = digest
    bundle_bytes = dump_bytes(bundle)
    bundle_path.write_bytes(bundle_bytes)

    manifest_path = run_directory / "run-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["track-a-bundle.json"] = hashlib.sha256(
        bundle_bytes
    ).hexdigest()
    manifest_path.write_bytes(dump_bytes(manifest))


def _zip_evidence_hash(path: Path) -> str:
    with zipfile.ZipFile(path, "r") as archive:
        return hashlib.sha256(archive.read("evidence/evidence.sqlite")).hexdigest()


def test_release_validation_reports_finalized_evidence_provenance(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    run_id = _workspace(root)

    report = validate_release_workspace(root, run_id=run_id)

    evidence = report["sqlite"]
    packet = json.loads(
        (root / "runs" / run_id / "final-review-packet.json").read_text(
            encoding="utf-8"
        )
    )
    assert evidence["status"] == "PASS"
    assert evidence["file_sha256"] == hashlib.sha256(
        (root / "evidence" / "evidence.sqlite").read_bytes()
    ).hexdigest()
    assert evidence["run_evidence_db_sha256"] == evidence["file_sha256"]
    assert evidence["snapshot_sha256"] == packet["snapshot_sha256"]
    assert evidence["packet_snapshot_sha256"] == packet["snapshot_sha256"]
    assert evidence["physical_file_hash_stable"] is True


def test_release_rejects_arbitrary_sqlite_database(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    run_id = _workspace(root)
    database = root / "evidence" / "evidence.sqlite"
    database.unlink()
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE evidence(id TEXT PRIMARY KEY)")

    report = validate_release_workspace(root, run_id=run_id)

    assert report["status"] == "FAIL"
    assert "SQLITE_VALIDATION_FAILED" in report["errors"]
    assert report["sqlite"]["reason_code"] == "EVIDENCE_DATABASE_NOT_FINALIZED"


def test_release_rejects_unfinalized_evidence_store(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    run_id = _workspace(root)
    database = root / "evidence" / "evidence.sqlite"
    database.unlink()
    with EvidenceStore(database, create=True):
        pass

    report = validate_release_workspace(root, run_id=run_id)

    assert report["status"] == "FAIL"
    assert "SQLITE_VALIDATION_FAILED" in report["errors"]
    assert report["sqlite"]["reason_code"] == "EVIDENCE_DATABASE_NOT_FINALIZED"


def test_release_rejects_packet_bound_to_different_evidence_snapshot(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    run_id = _workspace(root, packet_snapshot_sha256="0" * 64)

    report = validate_release_workspace(root, run_id=run_id)

    assert report["final_packet"]["status"] == "PASS"
    assert report["status"] == "FAIL"
    assert "SQLITE_VALIDATION_FAILED" in report["errors"]
    assert report["sqlite"]["reason_code"] == "PACKET_SNAPSHOT_MISMATCH"


def test_release_rejects_database_bytes_different_from_run_provenance(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    run_id = _workspace(root)
    database = root / "evidence" / "evidence.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA application_id = 225")

    report = validate_release_workspace(root, run_id=run_id)

    assert report["status"] == "FAIL"
    assert "SQLITE_VALIDATION_FAILED" in report["errors"]
    assert report["sqlite"]["reason_code"] == "RUN_EVIDENCE_DATABASE_HASH_MISMATCH"


def test_release_rejects_retrieval_index_content_changed_with_fresh_marker(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    run_id = _workspace(root)
    database = root / "evidence" / "evidence.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO evidence_fts(evidence_id, title, raw_text, normalized_text)
            VALUES('forged', 'Forged title', 'forged evidence', 'forged evidence')
            """
        )
    _bind_database_hash_to_run(
        root,
        run_id,
        hashlib.sha256(database.read_bytes()).hexdigest(),
    )

    report = validate_release_workspace(root, run_id=run_id)

    assert report["status"] == "FAIL"
    assert "SQLITE_VALIDATION_FAILED" in report["errors"]
    assert report["sqlite"]["reason_code"] == "EVIDENCE_INDEX_STALE"


def test_release_rejects_clause_index_content_changed_with_fresh_marker(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    run_id = _workspace(root)
    database = root / "evidence" / "evidence.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO clause_fts(
                clause_id, title, chapter, section, clause_number,
                raw_text, normalized_text
            ) VALUES('forged', 'Forged clause', NULL, NULL, NULL,
                     'forged text', 'forged text')
            """
        )
    _bind_database_hash_to_run(
        root,
        run_id,
        hashlib.sha256(database.read_bytes()).hexdigest(),
    )

    report = validate_release_workspace(root, run_id=run_id)

    assert report["status"] == "FAIL"
    assert "SQLITE_VALIDATION_FAILED" in report["errors"]
    assert report["sqlite"]["reason_code"] == "EVIDENCE_INDEX_STALE"


def test_release_rejects_stale_logical_evidence_snapshot(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    run_id = _workspace(root)
    database = root / "evidence" / "evidence.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE snapshot_meta SET value = ? WHERE key = 'snapshot_hash'",
            ("0" * 64,),
        )

    report = validate_release_workspace(root, run_id=run_id)

    assert report["status"] == "FAIL"
    assert "SQLITE_VALIDATION_FAILED" in report["errors"]
    assert report["sqlite"]["reason_code"] == "EVIDENCE_LOGICAL_SNAPSHOT_MISMATCH"


@pytest.mark.parametrize("suffix", ("-wal", "-shm", "-journal"))
def test_release_rejects_sqlite_sidecars(tmp_path: Path, suffix: str) -> None:
    root = tmp_path / "workspace"
    run_id = _workspace(root)
    database = root / "evidence" / "evidence.sqlite"
    database.with_name(database.name + suffix).write_bytes(b"sidecar")

    report = validate_release_workspace(root, run_id=run_id)

    assert report["status"] == "FAIL"
    assert "SQLITE_VALIDATION_FAILED" in report["errors"]
    assert report["sqlite"]["reason_code"] == "EVIDENCE_DATABASE_SIDECAR_PRESENT"


def test_release_rejects_dangling_sqlite_sidecar_symlink(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    run_id = _workspace(root)
    database = root / "evidence" / "evidence.sqlite"
    sidecar = database.with_name(database.name + "-wal")
    try:
        sidecar.symlink_to(tmp_path / "missing-sidecar-target")
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"file symlinks are unavailable on this platform: {error}")

    assert not sidecar.exists()
    assert sidecar.is_symlink()

    report = validate_release_workspace(root, run_id=run_id)

    assert report["status"] == "FAIL"
    assert "SQLITE_VALIDATION_FAILED" in report["errors"]
    assert report["sqlite"]["reason_code"] == "EVIDENCE_DATABASE_SIDECAR_PRESENT"


def test_release_rejects_stale_retrieval_index(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    run_id = _workspace(root)
    database = root / "evidence" / "evidence.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE retrieval_meta SET value = ? WHERE key = 'snapshot_hash'",
            ("0" * 64,),
        )

    report = validate_release_workspace(root, run_id=run_id)

    assert report["status"] == "FAIL"
    assert "SQLITE_VALIDATION_FAILED" in report["errors"]
    assert report["sqlite"]["reason_code"] == "EVIDENCE_INDEX_STALE"


def test_release_rejects_source_replacement_during_validation_snapshot_copy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    run_id = _workspace(root)
    database = root / "evidence" / "evidence.sqlite"
    original_copy = tmp_path / "original-evidence.sqlite"
    replacement = tmp_path / "replacement-evidence.sqlite"
    shutil.copyfile(database, replacement)
    connection = sqlite3.connect(replacement)
    try:
        connection.execute(
            "UPDATE retrieval_meta SET value = ? WHERE key = 'snapshot_hash'",
            ("0" * 64,),
        )
        connection.commit()
    finally:
        connection.close()

    swapped = False
    import evidence_review.release.evidence_database as evidence_database

    original_copyfile = evidence_database.shutil.copyfile

    def swap_source_for_copy(source: Path, destination: Path) -> Path:
        nonlocal swapped
        if Path(source) == database and not swapped:
            database.replace(original_copy)
            replacement.replace(database)
            swapped = True
            try:
                return original_copyfile(source, destination)
            finally:
                database.unlink()
                original_copy.replace(database)
        return original_copyfile(source, destination)

    monkeypatch.setattr(evidence_database.shutil, "copyfile", swap_source_for_copy)

    report = validate_release_workspace(root, run_id=run_id)

    assert swapped is True
    assert report["status"] == "FAIL"
    assert "SQLITE_VALIDATION_FAILED" in report["errors"]
    assert report["sqlite"]["reason_code"] == (
        "PHYSICAL_FILE_CHANGED_DURING_VALIDATION"
    )


def test_release_validation_detects_physical_database_mutation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    run_id = _workspace(root)
    original_exit = EvidenceStore.__exit__

    def mutate_after_close(
        store: EvidenceStore,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        original_exit(store, exc_type, exc, traceback)
        if store.read_only and store.path.name == "evidence.sqlite":
            with store.path.open("ab") as stream:
                stream.write(b"mutation")

    monkeypatch.setattr(EvidenceStore, "__exit__", mutate_after_close)

    report = validate_release_workspace(root, run_id=run_id)

    assert report["status"] == "FAIL"
    assert "SQLITE_VALIDATION_FAILED" in report["errors"]
    assert report["sqlite"]["reason_code"] == (
        "PHYSICAL_FILE_CHANGED_DURING_VALIDATION"
    )


def test_release_validator_rejects_external_evidence_symlink(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    run_id = _workspace(root)
    database = root / "evidence" / "evidence.sqlite"
    external = tmp_path / "outside" / "evidence.sqlite"
    external.parent.mkdir()
    shutil.copyfile(database, external)
    database.unlink()
    try:
        database.symlink_to(external)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"file symlinks are unavailable on this platform: {error}")

    report = validate_release_workspace(root, run_id=run_id)

    assert report["status"] == "FAIL"
    assert "SQLITE_VALIDATION_FAILED" in report["errors"]
    assert report["sqlite"]["reason_code"] == "EVIDENCE_DATABASE_PATH_UNTRUSTED"


def test_release_builder_rejects_external_evidence_symlink(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    run_id = _workspace(root)
    database = root / "evidence" / "evidence.sqlite"
    external = tmp_path / "outside" / "evidence.sqlite"
    external.parent.mkdir()
    shutil.copyfile(database, external)
    database.unlink()
    try:
        database.symlink_to(external)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"file symlinks are unavailable on this platform: {error}")

    output = tmp_path / "release"
    with pytest.raises(ValueError, match="EVIDENCE_DATABASE_PATH_UNTRUSTED"):
        build_evidence_release(root, output, run_id=run_id)
    assert not output.exists()


def test_release_builder_rejects_evidence_changed_after_preflight(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    run_id = _workspace(root)
    output = tmp_path / "release"
    import evidence_review.release.builder as builder

    original_preflight = builder._preflight_release

    def mutate_after_preflight(*args: object, **kwargs: object) -> object:
        inputs = original_preflight(*args, **kwargs)
        evidence_path = inputs.evidence
        with evidence_path.open("ab") as stream:
            stream.write(b"mutation")
        return inputs

    monkeypatch.setattr(builder, "_preflight_release", mutate_after_preflight)

    with pytest.raises(ValueError, match="RELEASE_EVIDENCE_STAGE_HASH_MISMATCH"):
        build_evidence_release(root, output, run_id=run_id)
    assert not output.exists()


def test_release_bundles_use_configured_verified_evidence_bytes(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    run_id = _workspace(root)
    default_database = root / "evidence" / "evidence.sqlite"
    configured_database = root / "evidence" / "configured-evidence.sqlite"
    shutil.copyfile(default_database, configured_database)
    with sqlite3.connect(default_database) as connection:
        connection.execute("PRAGMA application_id = 225")
    expected_hash = hashlib.sha256(configured_database.read_bytes()).hexdigest()

    output = tmp_path / "release"
    build_evidence_release(
        root,
        output,
        run_id=run_id,
        config=ReleaseConfig(evidence_db_name="configured-evidence.sqlite"),
    )

    assert _zip_evidence_hash(output / "codex-workspace.zip") == expected_hash
    assert _zip_evidence_hash(output / "chatgpt-web-runtime.zip") == expected_hash


def test_release_bundles_do_not_follow_workspace_database_replacement(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    run_id = _workspace(root)
    database = root / "evidence" / "evidence.sqlite"
    expected_hash = hashlib.sha256(database.read_bytes()).hexdigest()
    import evidence_review.packaging.codex_bundle as codex_bundle

    original_copy = codex_bundle._copy_file
    workspace_database_mutated = False

    def mutate_workspace_database_before_bundle_copy(
        source: Path,
        destination: Path,
    ) -> None:
        nonlocal workspace_database_mutated
        if (
            not workspace_database_mutated
            and Path(destination).as_posix().endswith("/evidence/evidence.sqlite")
        ):
            with sqlite3.connect(database) as connection:
                connection.execute("PRAGMA application_id = 225")
            workspace_database_mutated = True
        original_copy(source, destination)

    monkeypatch.setattr(
        codex_bundle,
        "_copy_file",
        mutate_workspace_database_before_bundle_copy,
    )

    output = tmp_path / "release"
    result = build_evidence_release(root, output, run_id=run_id)

    assert workspace_database_mutated is True
    assert result["status"] == "BLOCKED"
    assert "AUTOMATED_VALIDATION_FAILED" in result["reason_codes"]
    assert (
        hashlib.sha256((output / "evidence.sqlite").read_bytes()).hexdigest()
        == expected_hash
    )
    assert _zip_evidence_hash(output / "codex-workspace.zip") == expected_hash
    assert _zip_evidence_hash(output / "chatgpt-web-runtime.zip") == expected_hash


def test_release_validator_and_builder_reject_evidence_directory_symlink(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    run_id = _workspace(root)
    evidence_directory = root / "evidence"
    external_directory = tmp_path / "outside-evidence"
    external_directory.mkdir()
    shutil.copyfile(
        evidence_directory / "evidence.sqlite",
        external_directory / "evidence.sqlite",
    )
    evidence_directory.rename(root / "evidence-local")
    try:
        evidence_directory.symlink_to(external_directory, target_is_directory=True)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"directory symlinks are unavailable on this platform: {error}")

    report = validate_release_workspace(root, run_id=run_id)
    assert report["status"] == "FAIL"
    assert report["sqlite"]["reason_code"] == "EVIDENCE_DATABASE_PATH_UNTRUSTED"

    output = tmp_path / "release"
    with pytest.raises(ValueError, match="EVIDENCE_DATABASE_PATH_UNTRUSTED"):
        build_evidence_release(root, output, run_id=run_id)
    assert not output.exists()


def test_release_builder_rejects_symlinked_workspace_root(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    run_id = _workspace(root)
    linked_root = tmp_path / "workspace-link"
    try:
        linked_root.symlink_to(root, target_is_directory=True)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"directory symlinks are unavailable on this platform: {error}")

    report = validate_release_workspace(linked_root, run_id=run_id)
    assert report["status"] == "FAIL"
    assert report["final_packet"]["status"] == "FAIL"
    assert "symlink" in report["final_packet"]["error"]
    assert "SQLITE_VALIDATION_FAILED" in report["errors"]
    assert report["sqlite"]["status"] == "FAIL"

    output = tmp_path / "release"
    with pytest.raises(ValueError, match="symlink"):
        build_evidence_release(linked_root, output, run_id=run_id)
    assert not output.exists()


def test_release_rejects_packet_bound_to_a_different_run(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    run_id = _workspace(root)
    selected_packet = root / "runs" / run_id / "final-review-packet.json"
    packet_document = json.loads(selected_packet.read_text(encoding="utf-8"))
    packet_document["run_id"] = "RUN-ABCDEF0123456789ABCD"
    selected_packet.write_bytes(dump_bytes(packet_document))

    with pytest.raises(ValueError, match="run_id"):
        build_evidence_release(root, tmp_path / "release", run_id=run_id)


def test_release_requires_explicit_run_local_packet_selection(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    run_id = _workspace(root)
    packet = root / "runs" / run_id / "final-review-packet.json"
    output = tmp_path / "release"

    with pytest.raises(ValueError, match="run_id"):
        build_evidence_release(root, output)

    manifest = build_evidence_release(root, output, run_id=run_id)

    assert manifest["run_id"] == run_id
    assert manifest["packet_hash"] == hashlib.sha256(packet.read_bytes()).hexdigest()
    assert (output / "final-review-packet.json").read_bytes() == packet.read_bytes()
    assert not output.joinpath("runs", "final-review-packet.json").exists()


def test_release_rejects_incomplete_final_packet(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    run_id = _workspace(root)
    packet = root / "runs" / run_id / "final-review-packet.json"
    packet.write_bytes(json.dumps({"run_id": run_id}).encode("utf-8"))

    with pytest.raises(ValueError, match="final packet"):
        build_evidence_release(root, tmp_path / "release", run_id=run_id)


def test_release_rejects_tampered_final_packet(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    run_id = _workspace(root)
    packet = root / "runs" / run_id / "final-review-packet.json"
    document = json.loads(packet.read_text(encoding="utf-8"))
    document["human_decision"] = "SATISFIED"
    packet.write_bytes(json.dumps(document).encode("utf-8"))

    with pytest.raises(ValueError, match="final packet"):
        build_evidence_release(root, tmp_path / "release", run_id=run_id)


def test_release_validation_path_is_relative_and_candidate_hash_is_stable(
    tmp_path: Path,
) -> None:
    first_root = tmp_path / "first-location" / "workspace"
    second_root = tmp_path / "second-location" / "workspace"
    first_run_id = _workspace(first_root)
    second_run_id = _workspace(second_root)

    first = build_evidence_release(
        first_root,
        tmp_path / "first-release",
        run_id=first_run_id,
    )
    second = build_evidence_release(
        second_root,
        tmp_path / "second-release",
        run_id=second_run_id,
    )

    first_validation = json.loads(
        (tmp_path / "first-release" / "release-validation.json").read_text(
            encoding="utf-8"
        )
    )
    second_validation = json.loads(
        (tmp_path / "second-release" / "release-validation.json").read_text(
            encoding="utf-8"
        )
    )

    assert first_run_id == second_run_id
    assert first["candidate_hash"] == second["candidate_hash"]
    assert first_validation == second_validation
    assert first_validation["final_packet"]["path"] == (
        f"runs/{first_run_id}/final-review-packet.json"
    )
    validation_text = json.dumps(first_validation)
    assert str(first_root) not in validation_text
    assert str(second_root) not in validation_text


def test_release_builder_script_requires_run_id_option() -> None:
    repository_root = Path(__file__).parents[3]
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(repository_root / "src")

    completed = subprocess.run(
        [sys.executable, str(repository_root / "scripts" / "build_release.py"), "--help"],
        cwd=repository_root,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "--run-id" in completed.stdout


def test_release_blocks_until_exact_process_attestation_is_present(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    run_id = _workspace(root)
    blocked_output = tmp_path / "blocked"
    blocked = build_ansim_release(root, blocked_output, run_id=run_id)
    assert blocked["format"] == "evidence-review/release"
    assert blocked["release"] == "evidence-review-v1.0"
    assert blocked["status"] == "BLOCKED"
    assert blocked["reason_codes"] == ["PROCESS_ATTESTATION_MISSING"]
    assert blocked["attestation_assurance"] == "PROCESS_ATTESTATION"
    assert blocked["cryptographic_identity_verified"] is False
    assert blocked["expected_reviewer_id"] is None
    assert blocked["attestation"] is None
    assert blocked["tag_allowed"] is False

    validation = json.loads(
        (blocked_output / "release-validation.json").read_text(encoding="utf-8")
    )
    assert validation["format"] == "evidence-review/release-validation"
    assert validation["status"] == "PASS"
    output_validation = validation["release_output"]
    assert output_validation["format"] == "evidence-review/release-output-validation"
    assert output_validation["status"] == "PASS"
    assert {item["archive"] for item in output_validation["archives"]} == {
        "codex-workspace.zip",
        "chatgpt-web-runtime.zip",
    }

    candidate_hash = blocked["candidate_hash"]
    packet_hash = blocked["packet_hash"]
    assert isinstance(candidate_hash, str)
    assert isinstance(packet_hash, str)

    legacy_dir = root / "releases/ansim-v1.0"
    legacy_dir.mkdir(parents=True)
    (legacy_dir / "acceptance-record.json").write_text(
        json.dumps(_legacy_acceptance(candidate_hash, packet_hash)),
        encoding="utf-8",
    )
    legacy_blocked = build_ansim_release(
        root,
        tmp_path / "legacy-blocked",
        run_id=run_id,
    )
    assert legacy_blocked["status"] == "BLOCKED"
    assert legacy_blocked["reason_codes"] == ["PROCESS_ATTESTATION_MISSING"]

    attestation_dir = root / "releases/evidence-review-v1.0"
    attestation_dir.mkdir(parents=True)
    (attestation_dir / "human-attestation.json").write_text(
        json.dumps(
            _attestation(
                str(legacy_blocked["candidate_hash"]),
                str(legacy_blocked["packet_hash"]),
            )
        ),
        encoding="utf-8",
    )
    ready = build_ansim_release(root, tmp_path / "ready", run_id=run_id)
    assert ready["status"] == "RELEASE_READY"
    assert ready["reason_codes"] == []
    assert ready["tag_allowed"] is True
    assert ready["attestation_assurance"] == "PROCESS_ATTESTATION"
    assert ready["cryptographic_identity_verified"] is False
    assert isinstance(ready["attestation"], dict)
    assert (tmp_path / "ready/human-attestation.json").is_file()
    assert not (tmp_path / "ready/acceptance-record.json").exists()


def test_release_rejects_stale_attestation_hashes(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    run_id = _workspace(root)
    first = build_ansim_release(root, tmp_path / "first", run_id=run_id)
    attestation_dir = root / "releases/evidence-review-v1.0"
    attestation_dir.mkdir(parents=True)
    (attestation_dir / "human-attestation.json").write_text(
        json.dumps(_attestation("0" * 64, str(first["packet_hash"]))),
        encoding="utf-8",
    )

    blocked = build_ansim_release(root, tmp_path / "stale", run_id=run_id)

    assert blocked["status"] == "BLOCKED"
    assert blocked["reason_codes"] == ["PROCESS_ATTESTATION_INVALID"]
    assert blocked["tag_allowed"] is False


def test_release_rejects_configured_reviewer_identity_mismatch(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    run_id = _workspace(root)
    config = ReleaseConfig(expected_reviewer_id="reviewer-b@example.com")
    first = build_evidence_release(
        root,
        tmp_path / "first",
        run_id=run_id,
        config=config,
    )
    attestation_dir = root / "releases/evidence-review-v1.0"
    attestation_dir.mkdir(parents=True)
    (attestation_dir / "human-attestation.json").write_text(
        json.dumps(
            _attestation(
                str(first["candidate_hash"]),
                str(first["packet_hash"]),
                reviewer_id="reviewer-a@example.com",
            )
        ),
        encoding="utf-8",
    )

    blocked = build_evidence_release(
        root,
        tmp_path / "mismatch",
        run_id=run_id,
        config=config,
    )

    assert blocked["status"] == "BLOCKED"
    assert blocked["reason_codes"] == ["PROCESS_ATTESTATION_INVALID"]
    assert blocked["expected_reviewer_id"] == "reviewer-b@example.com"


def test_release_candidate_ignores_generated_python_files(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    run_id = _workspace(root)

    generated = (
        root
        / "src"
        / "evidence_review"
        / "packaging"
        / "__pycache__"
        / "generated.cpython-313.pyc"
    )
    generated.parent.mkdir(parents=True, exist_ok=True)
    generated.write_bytes(b"first-generated-bytecode")

    first = build_ansim_release(root, tmp_path / "first", run_id=run_id)

    generated.write_bytes(b"second-different-bytecode")

    egg_info = root / "src" / "evidence_review" / "noise.egg-info"
    egg_info.mkdir()
    (egg_info / "PKG-INFO").write_text(
        "generated metadata",
        encoding="utf-8",
    )

    second = build_ansim_release(root, tmp_path / "second", run_id=run_id)

    assert first["candidate_hash"] == second["candidate_hash"]

def test_release_preflight_failure_leaves_no_final_output(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    run_id = _workspace(root)
    (root / "evidence" / "evidence.sqlite").unlink()
    output = tmp_path / "release"

    with pytest.raises(FileNotFoundError):
        build_evidence_release(root, output, run_id=run_id)

    assert not output.exists()


def test_release_stage_failure_leaves_no_final_output_or_stage(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    run_id = _workspace(root)
    output = tmp_path / "release"

    def fail_zip(source: Path, target: Path) -> None:
        raise OSError("injected build failure")

    import evidence_review.release.builder as builder

    monkeypatch.setattr(builder, "_zip_directory", fail_zip)
    with pytest.raises(OSError, match="injected build failure"):
        build_evidence_release(root, output, run_id=run_id)

    assert not output.exists()
    assert not list(tmp_path.glob(".release.stage-*"))
