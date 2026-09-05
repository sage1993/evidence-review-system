from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
from types import ModuleType

import pytest


def _verified_artifacts() -> ModuleType:
    try:
        return importlib.import_module("evidence_review.abstention.verified_artifacts")
    except ModuleNotFoundError:
        pytest.fail("verified artifact snapshot module is missing")


def _write_run(
    tmp_path: Path,
    *,
    artifacts: dict[str, bytes],
    hashes: dict[str, str] | None = None,
) -> Path:
    run_id = "RUN-VERIFIED-SNAPSHOT"
    run_directory = tmp_path / run_id
    run_directory.mkdir(parents=True)
    effective_hashes = (
        {name: hashlib.sha256(data).hexdigest() for name, data in artifacts.items()}
        if hashes is None
        else hashes
    )
    for name, data in artifacts.items():
        (run_directory / name).write_bytes(data)
    (run_directory / "run-manifest.json").write_text(
        json.dumps({"run_id": run_id, "artifacts": effective_hashes}),
        encoding="utf-8",
    )
    return run_directory


def test_verify_run_snapshot_reads_each_required_artifact_once(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _verified_artifacts()
    artifacts = {
        "a.json": b'{"value":1}',
        "b.json": b'{"value":2}',
    }
    run_directory = _write_run(tmp_path, artifacts=artifacts)
    original = Path.read_bytes
    reads: dict[str, int] = {}

    def counted(path: Path) -> bytes:
        if path.name in artifacts:
            reads[path.name] = reads.get(path.name, 0) + 1
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", counted)

    snapshot = module.verify_run_snapshot(
        run_directory,
        required_artifacts=("a.json", "b.json"),
    )

    assert reads == {"a.json": 1, "b.json": 1}
    assert snapshot.document("a.json") == {"value": 1}
    assert snapshot.raw_bytes("b.json") == artifacts["b.json"]


def test_hash_mismatch_fails_before_invalid_json_is_exposed(tmp_path: Path) -> None:
    module = _verified_artifacts()
    run_directory = _write_run(
        tmp_path,
        artifacts={"a.json": b"not-json"},
        hashes={"a.json": "0" * 64},
    )

    with pytest.raises(ValueError, match="artifact hash mismatch: a.json"):
        module.verify_run_snapshot(run_directory, required_artifacts=("a.json",))


def test_invalid_utf8_or_json_fails_closed(tmp_path: Path) -> None:
    module = _verified_artifacts()
    invalid_values = (b"\xff", b"{not-json")

    for index, data in enumerate(invalid_values):
        directory = _write_run(tmp_path / str(index), artifacts={"a.json": data})
        with pytest.raises(ValueError, match="invalid JSON artifact: a.json"):
            module.verify_run_snapshot(directory, required_artifacts=("a.json",))


def test_required_artifact_names_must_be_unique_and_present(tmp_path: Path) -> None:
    module = _verified_artifacts()
    run_directory = _write_run(tmp_path, artifacts={"a.json": b"{}"})

    with pytest.raises(ValueError, match="required artifact names must be unique"):
        module.verify_run_snapshot(
            run_directory,
            required_artifacts=("a.json", "a.json"),
        )

    with pytest.raises(ValueError, match="run manifest is missing artifacts: b.json"):
        module.verify_run_snapshot(
            run_directory,
            required_artifacts=("a.json", "b.json"),
        )


def test_snapshot_content_authority_contains_no_paths(tmp_path: Path) -> None:
    module = _verified_artifacts()
    raw = b'{"value":1}'
    run_directory = _write_run(tmp_path, artifacts={"a.json": raw})

    snapshot = module.verify_run_snapshot(
        run_directory,
        required_artifacts=("a.json",),
    )
    artifact = snapshot.artifacts[0]

    assert artifact.name == "a.json"
    assert artifact.sha256 == hashlib.sha256(raw).hexdigest()
    assert artifact.raw_bytes == raw
    assert artifact.document == {"value": 1}
    assert not hasattr(artifact, "path")
    assert not any(isinstance(value, Path) for value in (artifact.raw_bytes, artifact.document))
