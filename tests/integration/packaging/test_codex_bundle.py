import json
from pathlib import Path

from ansim_review.packaging.codex_bundle import build_codex_bundle


def test_codex_bundle_contains_runtime_evidence_rules_skills_and_validation(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    package = root / "src" / "ansim_review"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (root / "evidence").mkdir()
    (root / "evidence" / "ansim-evidence.sqlite").write_bytes(
        b"SQLite format 3\0fixture"
    )
    (root / "rules" / "approved").mkdir(parents=True)
    (root / "rules" / "approved" / "R1.json").write_text(
        "{}",
        encoding="utf-8",
    )
    (root / "rules" / "manifests").mkdir()
    (root / "rules" / "manifests" / "active.json").write_text(
        "{}",
        encoding="utf-8",
    )
    (root / "AGENTS.md").write_text("# agents", encoding="utf-8")
    for index in range(1, 6):
        skill = root / f"skills/0{index}-skill"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(f"# skill {index}", encoding="utf-8")

    output = tmp_path / "bundle"
    manifest = build_codex_bundle(root, output)
    assert (output / "AGENTS.md").is_file()
    assert len(list((output / "skills").glob("*/SKILL.md"))) == 5
    assert (output / "src" / "ansim_review" / "__init__.py").is_file()
    assert (output / "evidence" / "ansim-evidence.sqlite").is_file()
    assert (output / "rules" / "approved" / "R1.json").is_file()
    assert (output / "rules" / "manifests" / "active.json").is_file()
    validation = (output / "VALIDATE.md").read_text(encoding="utf-8")
    assert "python -m ansim_review --help" in validation
    data = json.loads(
        (output / "bundle-manifest.json").read_text(encoding="utf-8")
    )
    assert data == manifest
    assert all(not Path(item["path"]).is_absolute() for item in data["files"])
