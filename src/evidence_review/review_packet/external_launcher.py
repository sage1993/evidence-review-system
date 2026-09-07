"""Open review URLs through the platform browser without blocking the run."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import os
import sys
import webbrowser
from collections.abc import Iterator

_SW_SHOWNORMAL = 1


def _registered_background_browsers() -> Iterator[webbrowser.BackgroundBrowser]:
    """Yield stdlib-discovered executable browser controllers in preference order."""
    webbrowser.get()
    for name in getattr(webbrowser, "_tryorder", ()) or ():
        try:
            browser = webbrowser.get(name)
        except webbrowser.Error:
            continue
        if isinstance(browser, webbrowser.BackgroundBrowser):
            yield browser


def _background_browser_command(
    browser: webbrowser.BackgroundBrowser,
    url: str,
) -> list[str]:
    arguments = [argument.replace("%s", url) for argument in browser.args]
    if not any("%s" in argument for argument in browser.args):
        arguments.append(url)
    return [browser.name, *arguments]


def _shell_execute_url(url: str) -> bool:
    """Ask Windows to open a URL through its registered shell association."""
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)  # type: ignore[attr-defined,unused-ignore]
    shell_execute = shell32.ShellExecuteW
    shell_execute.argtypes = [
        ctypes.wintypes.HWND,
        ctypes.wintypes.LPCWSTR,
        ctypes.wintypes.LPCWSTR,
        ctypes.wintypes.LPCWSTR,
        ctypes.wintypes.LPCWSTR,
        ctypes.c_int,
    ]
    shell_execute.restype = ctypes.wintypes.HINSTANCE
    result = shell_execute(None, "open", url, None, None, _SW_SHOWNORMAL)
    result_value = result if isinstance(result, int) else (result.value or 0)
    if result_value <= 32:
        raise OSError(f"Windows ShellExecuteW failed with code {result_value}")
    return True


def _open_windows_url(url: str) -> bool:
    last_error: BaseException | None = None
    startfile = getattr(os, "startfile", None)
    if startfile is not None:
        try:
            startfile(url)
            return True
        except OSError as error:
            last_error = error
    else:
        last_error = None

    try:
        return _shell_execute_url(url)
    except (AttributeError, OSError, ValueError) as error:
        last_error = error

    for browser in _registered_background_browsers():
        try:
            command = _background_browser_command(browser, url)
            os.spawnv(
                os.P_NOWAIT,
                browser.name,
                command,
            )
        except OSError as error:
            last_error = error
            continue
        return True

    if last_error is None:
        raise OSError("no Windows browser launcher is available")
    raise OSError("no Windows browser launcher could open the URL") from last_error


def open_external_url(url: str) -> bool:
    """Open a URL through the platform browser without exposing URL contents."""
    if sys.platform == "win32":
        return _open_windows_url(url)
    return webbrowser.open(url)


__all__ = ["open_external_url"]
