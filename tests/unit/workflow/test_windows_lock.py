from __future__ import annotations

import ctypes
import os
from pathlib import Path

import pytest

if os.name != "nt":
    pytest.skip("Windows file-lock backend", allow_module_level=True)

from ansim_review.workflow import windows_lock


def test_acquire_uses_blocking_exclusive_one_byte_range(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[int, int, int, int]] = []

    def fake_lock(
        handle: object,
        flags: int,
        reserved: int,
        low: int,
        high: int,
        overlapped: object,
    ) -> int:
        del handle, overlapped
        calls.append((flags, reserved, low, high))
        return 1

    monkeypatch.setattr(windows_lock, "_lock_file_ex", fake_lock)
    with (tmp_path / "lock").open("w+b") as stream:
        windows_lock.acquire_exclusive_file_lock(stream)

    assert calls == [(windows_lock.LOCKFILE_EXCLUSIVE_LOCK, 0, 1, 0)]


def test_release_uses_same_one_byte_range(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[int, int, int]] = []

    def fake_unlock(
        handle: object,
        reserved: int,
        low: int,
        high: int,
        overlapped: object,
    ) -> int:
        del handle, overlapped
        calls.append((reserved, low, high))
        return 1

    monkeypatch.setattr(windows_lock, "_unlock_file_ex", fake_unlock)
    with (tmp_path / "lock").open("w+b") as stream:
        windows_lock.release_file_lock(stream)

    assert calls == [(0, 1, 0)]


def test_acquire_preserves_win32_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_lock(*args: object) -> int:
        del args
        ctypes.set_last_error(5)
        return 0

    monkeypatch.setattr(windows_lock, "_lock_file_ex", fail_lock)
    with (tmp_path / "lock").open("w+b") as stream:
        with pytest.raises(OSError) as exc_info:
            windows_lock.acquire_exclusive_file_lock(stream)

    assert getattr(exc_info.value, "winerror", None) == 5


def test_release_preserves_win32_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_unlock(*args: object) -> int:
        del args
        ctypes.set_last_error(6)
        return 0

    monkeypatch.setattr(windows_lock, "_unlock_file_ex", fail_unlock)
    with (tmp_path / "lock").open("w+b") as stream:
        with pytest.raises(OSError) as exc_info:
            windows_lock.release_file_lock(stream)

    assert getattr(exc_info.value, "winerror", None) == 6
