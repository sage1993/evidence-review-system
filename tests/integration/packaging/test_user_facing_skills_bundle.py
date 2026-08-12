import shutil
from pathlib import Path

from ansim_review.packaging.codex_bundle import build_codex_bundle


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
    for index in range(1, 6):
        skill = root / f"skills/0{index}-skill"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(f"# skill {index}", encoding="utf-8")
    for name in ("ers-pdf", "ers-review"):
        skill = root / f"skills/{name}"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text(f"# {name}", encoding="utf-8")


def test_codex_bundle_includes_user_facing_ers_skills(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    _workspace(root)
    output = tmp_path / "bundle"

    build_codex_bundle(root, output)

    assert (output / ".agents/skills/ers-pdf/SKILL.md").is_file()
    assert (output / ".agents/skills/ers-review/SKILL.md").is_file()
    agents = (output / "AGENTS.md").read_text(encoding="utf-8")
    assert "$ERS_PDF" in agents
    assert "$ERS_REVIEW" in agents