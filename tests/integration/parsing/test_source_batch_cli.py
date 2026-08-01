from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ansim_review import cli
from ansim_review.canonical_json import dump_bytes


def _manifest(path: Path) -> None:
    path.write_bytes(
        dump_bytes(
            {
                "format": "evidence-review/source-batch",
                "version": 2,
                "sources": [
                    {
                        "source_path": "inputs/original/policy.pdf",
                        "role": "REFERENCE_DOCUMENT",
                        "document_id": None,
                        "display_title": None,
                        "parser": None,
                    }
                ],
            }
        )
    )


def test_primary_cli_name_is_generic_and_requires_a_command() -> None:
    parser = cli.build_parser()
    assert parser.prog == "evidence-review"
    with pytest.raises(SystemExit) as error:
        parser.parse_args([])
    assert error.value.code == 2


def test_source_batch_prepare_projects_states_without_creating_database(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    root = tmp_path / "batch"
    root.mkdir()
    manifest = tmp_path / "source-batch.json"
    _manifest(manifest)

    def fake_prepare(batch_root: Path, batch):
        assert batch_root == root
        assert batch.version == 2
        return (
            SimpleNamespace(
                role="REFERENCE_DOCUMENT",
                document_id="DOC-ABC",
                revision_id="DOC-ABC-123456789abc",
                source_sha256="b" * 64,
                parser_kind=None,
                state="PENDING_PARSER_OUTPUT",
                reason_codes=("PARSER_OUTPUT_REQUIRED",),
                can_ingest_reference=False,
                can_evaluate=False,
            ),
        )

    monkeypatch.setattr(cli, "prepare_source_batch", fake_prepare)
    exit_code = cli.main(
        [
            "source-batch",
            "prepare",
            "--root",
            str(root),
            "--manifest",
            str(manifest),
        ]
    )

    assert exit_code == 0
    document = json.loads(capsys.readouterr().out)
    assert document["format"] == "evidence-review/source-batch-cli-status"
    assert document["stage"] == "prepare"
    assert document["status"] == "PENDING"
    assert document["sources"][0]["state"] == "PENDING_PARSER_OUTPUT"
    assert document["sources"][0]["reason_codes"] == ["PARSER_OUTPUT_REQUIRED"]


def test_source_batch_ingest_routes_and_outputs_generic_status(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    root = tmp_path / "batch"
    root.mkdir()
    manifest = tmp_path / "source-batch.json"
    output = tmp_path / "evidence" / "evidence.sqlite"
    _manifest(manifest)

    def fake_import(batch_root: Path, batch, output_db: Path):
        assert batch_root == root
        assert batch.format == "evidence-review/source-batch"
        assert output_db == output
        return SimpleNamespace(
            output_db=output,
            snapshot_hash="a" * 64,
            counts={"documents": 1},
            sources=(
                SimpleNamespace(
                    role="REFERENCE_DOCUMENT",
                    document_id="DOC-ABC",
                    revision_id="DOC-ABC-123456789abc",
                    source_sha256="b" * 64,
                    parser_kind="OPENDATALOADER_JSON",
                    state="READY_TO_EVALUATE",
                    reason_codes=(),
                    can_ingest_reference=False,
                    can_evaluate=True,
                ),
            ),
        )

    monkeypatch.setattr(cli, "import_source_batch", fake_import)
    exit_code = cli.main(
        [
            "source-batch",
            "ingest",
            "--root",
            str(root),
            "--manifest",
            str(manifest),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    document = json.loads(capsys.readouterr().out)
    assert document["format"] == "evidence-review/source-batch-cli-status"
    assert document["stage"] == "ingest"
    assert document["status"] == "INGESTED"
    assert document["output_db"] == str(output)
    assert document["sources"][0]["document_id"] == "DOC-ABC"
    assert document["sources"][0]["state"] == "READY_TO_EVALUATE"
