from pathlib import Path

GUIDE = Path("docs/LEGACY_LINEAGE_MIGRATION.md")
EXAMPLE = Path("docs/examples/legacy-lineage-manifest.example.json")
README = Path("README.md")
LEGACY_VISUALS = Path("docs/LEGACY_VISUALS.md")


def test_lineage_docs_are_explicit_and_fail_closed() -> None:
    text = GUIDE.read_text(encoding="utf-8")
    for token in (
        "copy-on-write",
        "evidence-review/legacy-lineage-manifest",
        "LAW3",
        "DOC-ACFD68E34043268C",
        "source SHA-256",
        "BLOCKED",
        "schema version 2",
        "does not cryptographically verify reviewer identity",
        "evidence migrate-lineage",
        "Grist attachment",
        "reviewed-value conflict",
    ):
        assert token in text


def test_docs_explain_outputs_exit_codes_and_source_immutability() -> None:
    text = GUIDE.read_text(encoding="utf-8")
    for token in (
        "legacy-lineage-aliases.json",
        "legacy-lineage-migration-report.json",
        "Exit code 0",
        "Exit code 1",
        "Exit code 2",
        "PRAGMA integrity_check",
        "PRAGMA foreign_key_check",
        "source database remains byte-identical",
        "create-only",
    ):
        assert token in text


def test_example_is_not_executable_acceptance_authority() -> None:
    text = EXAMPLE.read_text(encoding="utf-8")
    assert "EXAMPLE_ONLY_NOT_REVIEWED" in text
    assert '"mappings": []' in text


def test_readme_and_legacy_visual_policy_link_the_workflow() -> None:
    readme = README.read_text(encoding="utf-8")
    visual_policy = LEGACY_VISUALS.read_text(encoding="utf-8")
    assert "LEGACY_LINEAGE_MIGRATION.md" not in readme
    assert "evidence migrate-lineage" not in readme
    assert "document lineage migration" in visual_policy
    assert "does not canonicalize legacy visual CSV" in visual_policy


def test_normal_paths_do_not_consume_alias_registry() -> None:
    importer = Path(
        "src/evidence_review/parsing/source_batch_importer.py"
    ).read_text(encoding="utf-8")
    visual = Path("src/evidence_review/parsing/visual_manifest.py").read_text(
        encoding="utf-8"
    )
    release = Path("src/evidence_review/release/builder.py").read_text(
        encoding="utf-8"
    )
    for text in (importer, visual, release):
        assert "legacy-lineage-aliases" not in text
