import tomllib
from importlib.resources import as_file, files
from pathlib import Path
from shutil import which
from subprocess import run

import pytest


def test_runtime_templates_styles_and_scripts_are_declared_as_package_data() -> None:
    root = Path(__file__).parents[3]
    configuration = tomllib.loads(
        (root / "pyproject.toml").read_text(encoding="utf-8")
    )
    package_data = configuration["tool"]["setuptools"]["package-data"]
    assert "schema.sql" in package_data["evidence_review.evidence"]
    assert "schema.sql" in package_data["evidence_review.review_matter"]
    assert "templates/*.md" in package_data["evidence_review.llm_layer"]
    assert "assets/*.css" in package_data["evidence_review.review_packet"]
    assert "assets/*.js" in package_data["evidence_review.review_packet"]


def test_canonical_namespace_can_read_runtime_package_data() -> None:
    schema = files("evidence_review.evidence").joinpath("schema.sql")
    assert schema.is_file()

    templates = files("evidence_review.llm_layer").joinpath("templates")
    assert templates.is_dir()
    assert templates.joinpath("question-planner.md").is_file()
    assert templates.joinpath("track-a.md").is_file()
    assert templates.joinpath("track-b.md").is_file()

    assets = files("evidence_review.review_packet").joinpath("assets")
    assert assets.is_dir()
    assert any(item.name.endswith(".css") for item in assets.iterdir())
    assert assets.joinpath("review.js").is_file()


def test_packaged_workbench_script_matches_source_and_parses_in_node() -> None:
    node = which("node")
    if node is None:
        pytest.skip("node is unavailable for Workbench asset syntax validation")

    root = Path(__file__).parents[3]
    source = root / "src" / "evidence_review" / "workbench" / "assets" / "workbench.js"
    packaged = files("evidence_review.workbench").joinpath("assets", "workbench.js")

    assert packaged.read_text(encoding="utf-8") == source.read_text(encoding="utf-8")
    for script in (source,):
        result = run([node, "--check", str(script)], check=False, capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    with as_file(packaged) as packaged_script:
        result = run(
            [node, "--check", str(packaged_script)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
