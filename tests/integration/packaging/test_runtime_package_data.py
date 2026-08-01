import tomllib
from pathlib import Path


def test_runtime_templates_and_styles_are_declared_as_package_data() -> None:
    root = Path(__file__).parents[3]
    configuration = tomllib.loads(
        (root / "pyproject.toml").read_text(encoding="utf-8")
    )
    package_data = configuration["tool"]["setuptools"]["package-data"]
    assert "templates/*.md" in package_data["ansim_review.llm_layer"]
    assert "assets/*.css" in package_data["ansim_review.review_packet"]
