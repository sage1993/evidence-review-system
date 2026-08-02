from pathlib import Path

README = Path("README.md")
OFFLINE = Path("docs/OFFLINE_EXECUTION.md")


def test_final_release_output_verification_is_documented() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in (README, OFFLINE)
    )

    for required in (
        "bundle-manifest.json",
        "runtime-manifest.json",
        "RELEASE_OUTPUT_VALIDATION_FAILED",
        "without extracting",
        "case-fold collisions",
        "SHA-256",
    ):
        assert required in combined
