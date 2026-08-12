"""Blocking Windows byte-range locks for the workflow journal."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from typing import BinaryIO, Protocol, cast

if os.name == "nt":
    import msvcrt


LOCKFILE_EXCLUSIVE_LOCK = 0x00000002


class _MsvcrtApi(Protocol):
    def get_osfhandle(self, file_descriptor: int) -> int:
        ...


class _OverlappedOffset(ctypes.Structure):
    _fields_ = [
        ("Offset", wintypes.DWORD),
        ("OffsetHigh", wintypes.DWORD),
    ]


class _OverlappedUnion(ctypes.Union):
    _anonymous_ = ("offset",)
    _fields_ = [
        ("offset", _OverlappedOffset),
        ("Pointer", wintypes.LPVOID),
    ]


class _Overlapped(ctypes.Structure):
    _anonymous_ = ("union",)
    _fields_ = [
        ("Internal", ctypes.c_size_t),
        ("InternalHigh", ctypes.c_size_t),
        ("union", _OverlappedUnion),
        ("hEvent", wintypes.HANDLE),
    ]


if os.name == "nt":
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _lock_file_ex = _kernel32.LockFileEx
    _lock_file_ex.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(_Overlapped),
    ]
    _lock_file_ex.restype = wintypes.BOOL
    _unlock_file_ex = _kernel32.UnlockFileEx
    _unlock_file_ex.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(_Overlapped),
    ]
    _unlock_file_ex.restype = wintypes.BOOL


def acquire_exclusive_file_lock(stream: BinaryIO) -> None:
    """Acquire the first byte of ``stream`` with a blocking exclusive lock."""
    api = cast(_MsvcrtApi, msvcrt)
    handle = wintypes.HANDLE(api.get_osfhandle(stream.fileno()))
    overlapped = _Overlapped()
    ctypes.set_last_error(0)
    result = _lock_file_ex(
        handle,
        LOCKFILE_EXCLUSIVE_LOCK,
        0,
        1,
        0,
        ctypes.byref(overlapped),
    )
    if not result:
        raise ctypes.WinError(ctypes.get_last_error())


def release_file_lock(stream: BinaryIO) -> None:
    """Release the first byte of ``stream``."""
    api = cast(_MsvcrtApi, msvcrt)
    handle = wintypes.HANDLE(api.get_osfhandle(stream.fileno()))
    overlapped = _Overlapped()
    ctypes.set_last_error(0)
    result = _unlock_file_ex(
        handle,
        0,
        1,
        0,
        ctypes.byref(overlapped),
    )
    if not result:
        raise ctypes.WinError(ctypes.get_last_error())
