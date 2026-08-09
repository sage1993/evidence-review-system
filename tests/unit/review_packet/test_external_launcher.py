from __future__ import annotations

import pytest

from ansim_review.review_packet import external_launcher


def test_windows_launcher_falls_back_to_registered_browser_without_waiting(
    monkeypatch,
) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def denied_startfile(_url: str) -> None:
        raise OSError("ShellExecute denied")

    class FakeBrowser(external_launcher.webbrowser.BackgroundBrowser):
        def __init__(self) -> None:
            super().__init__("C:/Browser/browser.exe")
            self.args = ["--new-tab", "%s"]

    def fake_spawnv(mode: int, path: str, command: list[str]) -> int:
        calls.append((command, {"mode": mode, "path": path}))
        return 1234

    def denied_win_dll(*_args: object, **_kwargs: object) -> object:
        raise OSError("ShellExecute unavailable")

    monkeypatch.setattr(external_launcher.ctypes, "WinDLL", denied_win_dll)
    monkeypatch.setattr(external_launcher.sys, "platform", "win32")
    monkeypatch.setattr(external_launcher.os, "startfile", denied_startfile)
    monkeypatch.setattr(external_launcher.webbrowser, "_tryorder", ["fake-browser"])
    monkeypatch.setattr(
        external_launcher.webbrowser,
        "get",
        lambda name=None: FakeBrowser() if name == "fake-browser" else None,
    )
    monkeypatch.setattr(external_launcher.os, "spawnv", fake_spawnv)

    assert external_launcher.open_external_url("http://127.0.0.1:8123/runs/RUN-1/token/review")
    assert calls == [
        (
            [
                "C:/Browser/browser.exe",
                "--new-tab",
                "http://127.0.0.1:8123/runs/RUN-1/token/review",
            ],
            {"mode": external_launcher.os.P_NOWAIT, "path": "C:/Browser/browser.exe"},
        )
    ]


def test_windows_launcher_uses_shell_association_before_browser_process(monkeypatch) -> None:
    calls: list[tuple[object, ...]] = []

    class FakeShellExecute:
        argtypes: list[object] | None = None
        restype: object | None = None

        def __call__(self, *args: object) -> int:
            calls.append(args)
            return 42

    class FakeShell32:
        ShellExecuteW = FakeShellExecute()

    def denied_startfile(_url: str) -> None:
        raise OSError("startfile denied")

    monkeypatch.setattr(external_launcher.sys, "platform", "win32")
    monkeypatch.setattr(external_launcher.os, "startfile", denied_startfile)
    monkeypatch.setattr(
        external_launcher.ctypes,
        "WinDLL",
        lambda *_args, **_kwargs: FakeShell32(),
    )
    monkeypatch.setattr(
        external_launcher.os,
        "spawnv",
        lambda *_args, **_kwargs: pytest.fail("direct browser fallback must be last resort"),
    )

    url = "http://127.0.0.1:8123/runs/RUN-1/token/review"
    assert external_launcher.open_external_url(url)
    assert calls == [(None, "open", url, None, None, external_launcher._SW_SHOWNORMAL)]


def test_windows_startfile_success_does_not_spawn_a_second_launcher(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(external_launcher.sys, "platform", "win32")
    monkeypatch.setattr(
        external_launcher.os,
        "startfile",
        lambda url: calls.append(url),
    )
    monkeypatch.setattr(
        external_launcher.os,
        "spawnv",
        lambda *_args, **_kwargs: pytest.fail("fallback must not run"),
    )

    assert external_launcher.open_external_url("http://127.0.0.1:8123/review")
    assert calls == ["http://127.0.0.1:8123/review"]


def test_windows_launcher_fails_closed_when_all_launchers_fail(monkeypatch) -> None:
    class FakeBrowser(external_launcher.webbrowser.BackgroundBrowser):
        def __init__(self) -> None:
            super().__init__("C:/Browser/browser.exe")

    def denied_startfile(_url: str) -> None:
        raise OSError("ShellExecute denied")

    def denied_win_dll(*_args: object, **_kwargs: object) -> object:
        raise OSError("ShellExecute unavailable")

    def denied_spawnv(*_args: object, **_kwargs: object) -> None:
        raise OSError("browser process denied")

    monkeypatch.setattr(external_launcher.sys, "platform", "win32")
    monkeypatch.setattr(external_launcher.os, "startfile", denied_startfile)
    monkeypatch.setattr(external_launcher.ctypes, "WinDLL", denied_win_dll)
    monkeypatch.setattr(external_launcher.webbrowser, "_tryorder", ["fake-browser"])
    monkeypatch.setattr(
        external_launcher.webbrowser,
        "get",
        lambda name=None: FakeBrowser() if name in (None, "fake-browser") else None,
    )
    monkeypatch.setattr(external_launcher.os, "spawnv", denied_spawnv)

    with pytest.raises(OSError, match="browser launcher") as error:
        external_launcher.open_external_url(
            "http://127.0.0.1:8123/runs/RUN-1/token/review"
        )
    assert "http://127.0.0.1:8123/runs/RUN-1/token/review" not in str(error.value)


def test_non_windows_uses_webbrowser_without_windows_fallback(monkeypatch) -> None:
    calls: list[str] = []

    monkeypatch.setattr(external_launcher.sys, "platform", "linux")
    monkeypatch.setattr(
        external_launcher.webbrowser,
        "open",
        lambda url: calls.append(url) or True,
    )
    monkeypatch.delattr(external_launcher.os, "startfile", raising=False)

    assert external_launcher.open_external_url("http://127.0.0.1:8123/review")
    assert calls == ["http://127.0.0.1:8123/review"]
