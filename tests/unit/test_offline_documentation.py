from pathlib import Path


DOCUMENT = Path("docs/OFFLINE_EXECUTION.md")


def test_offline_documentation_separates_assurance_levels() -> None:
    text = DOCUMENT.read_text(encoding="utf-8")

    for required in (
        "APPLICATION_OFFLINE_GUARD",
        "OS_ISOLATED",
        "cryptographic_network_isolation_verified",
        "127.0.0.0/8",
        "::1",
        "--network none",
        "New-NetFirewallRule",
        "native extension",
        "manifest",
    ):
        assert required in text
