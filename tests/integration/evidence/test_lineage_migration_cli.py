from __future__ import annotations

import json
from pathlib import Path

import pytest

from ansim_review import cli
from ansim_review.evidence.lineage_migration import LegacyLineageMigrationResult


def _result(tmp_path: Path) -> LegacyLineageMigrationResult:
    output = (tmp_path / "out" / "evidence.sqlite").resolve()
    return LegacyLineageMigrationResult(
        output_database=output,
        aliases_path=output.with_name(
            f"{output.name}.legacy-lineage-aliases.json"
        ),
        report_path=output.with_name(
            f"{output.name}.legacy-lineage-migration-report.json"
        ),
        output_sha256="a" * 64,
        logical_lineage_digest="b" * 64,
        removed_counts={"documents": 1},
    )


def test_migrate_lineage_cli_outputs_canonical_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    expected = _result(tmp_path)
    calls: list[tuple[Path, Path, Path]] = []

    def fake_apply(source: Path, manifest: Path, output: Path):
        calls.append((source, manifest, output))
        return expected

    monkeypatch.setattr(cli, "apply_legacy_lineage_migration", fake_apply, raising=False)
    source = tmp_path / "source.sqlite"
    manifest = tmp_path / "manifest.json"
    output = tmp_path / "out" / "evidence.sqlite"

    exit_code = cli.main(
        [
            "evidence",
            "migrate-lineage",
            "--source",
            str(source),
            "--manifest",
            str(manifest),
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    assert calls == [(source, manifest, output)]
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "format": "evidence-review/legacy-lineage-migration-status",
        "version": 1,
        "status": "MIGRATED",
        "output_database": str(expected.output_database),
        "aliases": str(expected.aliases_path),
        "report": str(expected.report_path),
        "output_sha256": "a" * 64,
        "logical_lineage_digest": "b" * 64,
    }


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (FileExistsError("output exists"), 1),
        (ValueError("SOURCE_DATABASE_HASH_MISMATCH"), 2),
        (OSError("read failed"), 2),
    ],
)
def test_migrate_lineage_cli_uses_declared_error_exit_codes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
    expected: int,
) -> None:
    def fake_apply(source: Path, manifest: Path, output: Path):
        raise error

    monkeypatch.setattr(cli, "apply_legacy_lineage_migration", fake_apply, raising=False)
    exit_code = cli.main(
        [
            "evidence",
            "migrate-lineage",
            "--source",
            str(tmp_path / "source.sqlite"),
            "--manifest",
            str(tmp_path / "manifest.json"),
            "--output",
            str(tmp_path / "output.sqlite"),
        ]
    )

    assert exit_code == expected
    assert str(error) in capsys.readouterr().err


def test_migrate_lineage_help_lists_required_paths(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.main(["evidence", "migrate-lineage", "--help"])

    assert raised.value.code == 0
    output = capsys.readouterr().out
    assert "--source" in output
    assert "--manifest" in output
    assert "--output" in output
