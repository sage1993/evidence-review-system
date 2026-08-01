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
    cache = package / "__pycache__"
    cache.mkdir()
    (cache / "generated.cpython-313.pyc").write_bytes(b"generated")
    egg_info = package / "noise.egg-info"
    egg_info.mkdir()
    (egg_info / "PKG-INFO").write_text("generated", encoding="utf-8")
    (root / "evidence").mkdir()
    (root / "evidence" / "evidence.sqlite").write_bytes(
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
    assert not (
        output
        / "src"
        / "ansim_review"
        / "__pycache__"
        / "generated.cpython-313.pyc"
    ).exists()
    assert not (
        output
        / "src"
        / "ansim_review"
        / "noise.egg-info"
    ).exists()
    assert (output / "evidence" / "evidence.sqlite").is_file()
    assert (output / "rules" / "approved" / "R1.json").is_file()
    assert (output / "rules" / "manifests" / "active.json").is_file()
    validation = (output / "VALIDATE.md").read_text(encoding="utf-8")
    assert "python -m ansim_review --help" in validation
    data = json.loads(
        (output / "bundle-manifest.json").read_text(encoding="utf-8")
    )
    assert data == manifest
    assert data["format"] == "evidence-review/codex-workspace"
    assert all(not Path(item["path"]).is_absolute() for item in data["files"])
    assert all("__pycache__" not in item["path"] for item in data["files"])
    assert all(not item["path"].endswith(".pyc") for item in data["files"])
    assert all(".egg-info/" not in item["path"] for item in data["files"])
