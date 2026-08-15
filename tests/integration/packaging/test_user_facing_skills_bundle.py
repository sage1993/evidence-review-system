import shutil
from pathlib import Path

from evidence_review.packaging.codex_bundle import build_codex_bundle


def _workspace(root: Path) -> None:
    repository_root = Path(__file__).parents[3]
    shutil.copytree(
        repository_root / "src/evidence_review",
        root / "src/evidence_review",
    )
    shutil.copytree(
        repository_root / "src/ansim_review",
        root / "src/ansim_review",
    )
    (root / "evidence").mkdir()
    (root / "evidence" / "evidence.sqlite").write_bytes(
        b"SQLite format 3\0fixture"
    )
    (root / "rules" / "approved").mkdir(parents=True)
    (root / "rules" / "approved" / "R1.json").write_text(
        "{}", encoding="utf-8"
    )
    (root / "rules" / "manifests").mkdir(parents=True)
    (root / "rules" / "manifests" / "active.json").write_text(
        "{}", encoding="utf-8"
    )
    (root / "AGENTS.md").write_text("# agents", encoding="utf-8")
    for name in ("ers-pdf", "ers-review"):
        skill = root / f"skills/{name}"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(f"# {name}", encoding="utf-8")


def test_repository_publishes_only_current_ers_skill_directories() -> None:
    repository_root = Path(__file__).parents[3]
    skills_root = repository_root / "skills"

    skill_directories = sorted(path.name for path in skills_root.iterdir() if path.is_dir())

    assert skill_directories == ["ers-pdf", "ers-review"]
    assert not (skills_root / "VALIDATION.json").exists()


def test_codex_bundle_includes_only_user_facing_ers_skills(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    _workspace(root)
    output = tmp_path / "bundle"

    manifest = build_codex_bundle(root, output)

    assert (output / ".agents/skills/ers-pdf/SKILL.md").is_file()
    assert (output / ".agents/skills/ers-review/SKILL.md").is_file()
    assert not (output / "skills").exists()
    manifest_paths = {entry["path"] for entry in manifest["files"]}
    assert ".agents/skills/ers-pdf/SKILL.md" in manifest_paths
    assert ".agents/skills/ers-review/SKILL.md" in manifest_paths
    assert not any(path.startswith("skills/") for path in manifest_paths)
    agents = (output / "AGENTS.md").read_text(encoding="utf-8")
    assert "$ERS_PDF" in agents
    assert "$ERS_REVIEW" in agents
