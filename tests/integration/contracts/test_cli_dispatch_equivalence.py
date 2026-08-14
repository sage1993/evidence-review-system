from __future__ import annotations

from types import SimpleNamespace

import pytest

import ansim_review.cli as compatibility_cli
import ansim_review.command_dispatch as command_dispatch
import ansim_review.entrypoint as compatibility_entrypoint
import evidence_review.cli as public_cli
from ansim_review.cli_parser import build_parser


def test_all_entrypoints_delegate_to_the_same_business_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_dispatch(arguments: list[str] | None = None) -> int:
        calls.append(tuple(arguments or ()))
        return 17

    monkeypatch.setattr(command_dispatch, "dispatch", fake_dispatch)
    monkeypatch.setattr(
        public_cli,
        "preflight_runtime",
        lambda: SimpleNamespace(status="OK"),
    )

    assert public_cli.main(["query"]) == 17
    assert compatibility_cli.main(["query"]) == 17
    assert compatibility_entrypoint.main(["query"]) == 17
    assert calls == [("query",), ("query",), ("query",)]


def test_public_diagnostic_preflight_remains_outside_business_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Result:
        status = "SOURCE_MISMATCH"

        def to_document(self) -> dict[str, object]:
            return {"status": self.status}

    monkeypatch.setattr(public_cli, "preflight_runtime", lambda: Result())

    def unexpected_dispatch(arguments: list[str] | None = None) -> int:
        raise AssertionError(f"business dispatch should not run: {arguments}")

    monkeypatch.setattr(command_dispatch, "dispatch", unexpected_dispatch)

    assert public_cli.main(["query"]) == 2


def test_legacy_grist_command_is_not_part_of_current_parser() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit) as caught:
        parser.parse_args(["legacy", "validate-grist-qa"])

    assert caught.value.code == 2


def test_command_dispatch_is_the_only_business_dispatch_function() -> None:
    assert compatibility_cli.main.__module__ == "ansim_review.cli"
    assert compatibility_entrypoint.main.__module__ == "ansim_review.entrypoint"
    assert callable(command_dispatch.dispatch)
