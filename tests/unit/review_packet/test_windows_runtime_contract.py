from __future__ import annotations

import ctypes
import os
import sys

import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="Windows launcher contract")
def test_windows_runtime_exposes_required_shell_launcher_apis() -> None:
    startfile = getattr(os, "startfile", None)
    assert callable(startfile)

    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    assert callable(shell32.ShellExecuteW)
