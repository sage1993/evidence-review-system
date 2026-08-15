import tomllib
from importlib.resources import files
from pathlib import Path


def test_runtime_templates_styles_and_scripts_are_declared_as_package_data() -> None:
    root = Path(__file__).parents[3]
    configuration = tomllib.loads(
        (root / "pyproject.toml").read_text(encoding="utf-8")
    )
    package_data = configuration["tool"]["setuptools"]["package-data"]
    assert "schema.sql" in package_data["evidence_review.evidence"]
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
