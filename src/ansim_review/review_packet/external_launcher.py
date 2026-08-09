"""Open review URLs through the platform browser without blocking the run."""

from __future__ import annotations

import os
import sys
import webbrowser
from collections.abc import Iterator


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


def _open_windows_url(url: str) -> bool:
    startfile = getattr(os, "startfile", None)
    if startfile is not None:
        try:
            startfile(url)
            return True
        except OSError as error:
            last_error: OSError | None = error
    else:
        last_error = None

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
