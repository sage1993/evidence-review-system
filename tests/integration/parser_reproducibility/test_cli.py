from __future__ import annotations

import hashlib
import json
from pathlib import Path

from evidence_review.command_dispatch import main
from tests.unit.parser_reproducibility._helpers import (
    write_config,
    write_pdf,
    write_run,
    write_source_manifest,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_reproducibility_cli_writes_semantic_report(tmp_path: Path) -> None:
    source = write_pdf(tmp_path / "source.pdf")
    run_a = write_run(tmp_path / "run-a", source)
    run_b = write_run(tmp_path / "run-b", source)
    config = write_config(tmp_path / "config.json")
    output = tmp_path / "report.json"

    exit_code = main(
        [
            "parser",
            "reproducibility",
            "validate",
            "--source",
            str(source),
            "--run-a",
            str(run_a),
            "--run-b",
            str(run_b),
            "--config",
            str(config),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "SEMANTICALLY_IDENTICAL"
    assert report["differences"] == []


def test_reproducibility_cli_mismatch_and_create_only(tmp_path: Path) -> None:
    source = write_pdf(tmp_path / "source.pdf")
    run_a = write_run(tmp_path / "run-a", source, content="Alpha")
    run_b = write_run(tmp_path / "run-b", source, content="Beta")
    config = write_config(tmp_path / "config.json")
    output = tmp_path / "report.json"
    arguments = [
        "parser",
        "reproducibility",
        "validate",
        "--source",
        str(source),
        "--run-a",
        str(run_a),
        "--run-b",
        str(run_b),
        "--config",
        str(config),
        "--output",
        str(output),
    ]

    assert main(arguments) == 1
    before = sha256(output)
    assert main(arguments) == 2
    assert sha256(output) == before


def test_reproducibility_cli_rejects_nonfinite_artifact(tmp_path: Path) -> None:
    source = write_pdf(tmp_path / "source.pdf")
    run_a = write_run(tmp_path / "run-a", source)
    run_b = write_run(tmp_path / "run-b", source)
    (run_a / "document.json").write_text(
        '{"number of pages":1,"kids":[{"value":NaN}]}',
        encoding="utf-8",
    )
    config = write_config(tmp_path / "config.json")
    output = tmp_path / "report.json"

    exit_code = main(
        [
            "parser",
            "reproducibility",
            "validate",
            "--source",
            str(source),
            "--run-a",
            str(run_a),
            "--run-b",
            str(run_b),
            "--config",
            str(config),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 3
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "PARSER_FAILED"
    assert report["findings"][0]["code"] == "PARSER_ARTIFACT_INVALID"


def test_warning_cli_uses_manifest_without_source_pdf(tmp_path: Path) -> None:
    source = write_pdf(tmp_path / "source.pdf")
    run = write_run(
        tmp_path / "run",
        source,
        warning="page 1: inspect layout",
    )
    source_manifest = write_source_manifest(
        tmp_path / "source-batch.json",
        run,
    )
    config = write_config(tmp_path / "config.json")
    warning_output = tmp_path / "warnings.json"
    queue_output = tmp_path / "queue.json"
    source.unlink()

    exit_code = main(
        [
            "parser",
            "warnings",
            "collect",
            "--source-manifest",
            str(source_manifest),
            "--parser-artifacts",
            str(run),
            "--config",
            str(config),
            "--warning-output",
            str(warning_output),
            "--queue-output",
            str(queue_output),
        ]
    )

    assert exit_code == 0
    warning_report = json.loads(warning_output.read_text(encoding="utf-8"))
    queue = json.loads(queue_output.read_text(encoding="utf-8"))
    assert len(warning_report["warnings"]) == 1
    assert queue["entries"][0]["status"] == "REVIEW_REQUIRED"


def test_warning_cli_rolls_back_both_outputs_when_one_exists(
    tmp_path: Path,
) -> None:
    source = write_pdf(tmp_path / "source.pdf")
    run = write_run(tmp_path / "run", source, warning="page 1: warning")
    source_manifest = write_source_manifest(
        tmp_path / "source-batch.json",
        run,
    )
    config = write_config(tmp_path / "config.json")
    warning_output = tmp_path / "warnings.json"
    queue_output = tmp_path / "queue.json"
    queue_output.write_text("DO-NOT-OVERWRITE", encoding="utf-8")
    before = sha256(queue_output)

    exit_code = main(
        [
            "parser",
            "warnings",
            "collect",
            "--source-manifest",
            str(source_manifest),
            "--parser-artifacts",
            str(run),
            "--config",
            str(config),
            "--warning-output",
            str(warning_output),
            "--queue-output",
            str(queue_output),
        ]
    )

    assert exit_code == 2
    assert not warning_output.exists()
    assert sha256(queue_output) == before


def test_warning_cli_authority_failure_creates_no_output(tmp_path: Path) -> None:
    source = write_pdf(tmp_path / "source.pdf")
    run = write_run(tmp_path / "run", source)
    source_manifest = write_source_manifest(
        tmp_path / "source-batch.json",
        run,
        parser_kind="OTHER_PARSER",
    )
    config = write_config(tmp_path / "config.json")
    warning_output = tmp_path / "warnings.json"
    queue_output = tmp_path / "queue.json"

    exit_code = main(
        [
            "parser",
            "warnings",
            "collect",
            "--source-manifest",
            str(source_manifest),
            "--parser-artifacts",
            str(run),
            "--config",
            str(config),
            "--warning-output",
            str(warning_output),
            "--queue-output",
            str(queue_output),
        ]
    )

    assert exit_code == 2
    assert not warning_output.exists()
    assert not queue_output.exists()
