from __future__ import annotations

import pytest

import ansim_review.cli as compatibility_cli
import ansim_review.command_dispatch as command_dispatch
import ansim_review.entrypoint as compatibility_entrypoint
from ansim_review.cli_parser import build_parser


def test_compatibility_modules_delegate_to_the_same_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, ...]] = []

    def fake_dispatch(arguments: list[str] | None = None) -> int:
        calls.append(tuple(arguments or ()))
        return 17

    monkeypatch.setattr(command_dispatch, "dispatch", fake_dispatch)

    assert compatibility_cli.main(["query"]) == 17
    assert compatibility_entrypoint.main(["query"]) == 17
    assert calls == [("query",), ("query",)]


def test_legacy_grist_command_is_not_part_of_current_parser() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit) as caught:
        parser.parse_args(["legacy", "validate-grist-qa"])

    assert caught.value.code == 2


def test_command_dispatch_is_the_only_business_dispatch_function() -> None:
    assert compatibility_cli.main.__module__ == "ansim_review.cli"
    assert compatibility_entrypoint.main.__module__ == "ansim_review.entrypoint"
    assert callable(command_dispatch.dispatch)
