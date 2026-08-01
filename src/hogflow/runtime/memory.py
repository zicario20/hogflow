"""Standard-library process memory sampling for runtime heartbeats."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from typing import Callable

from hogflow.runtime.models import ProcessMemorySnapshot

Clock = Callable[[], datetime]


class StandardProcessMemoryProbe:
    """Read process resident memory without starting tracemalloc or history.

    Windows uses the process API. Linux reads the current process stat file and
    uses ``resource`` for peak RSS. Unsupported or failed probes return an
    explicit unavailable sample instead of failing the counting runtime.
    """

    def __init__(self, *, clock: Clock | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def snapshot(self) -> ProcessMemorySnapshot:
        captured_at = self._clock()
        try:
            if os.name == "nt":
                resident, peak = _windows_memory()
            else:
                resident, peak = _posix_memory()
            return ProcessMemorySnapshot(captured_at, True, resident, max(resident, peak))
        except (OSError, RuntimeError, ValueError, AttributeError):
            return ProcessMemorySnapshot(captured_at, False, 0, 0)


def _windows_memory() -> tuple[int, int]:
    import ctypes
    from ctypes import wintypes

    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = (
            ("cb", wintypes.DWORD),
            ("page_fault_count", wintypes.DWORD),
            ("peak_working_set_size", ctypes.c_size_t),
            ("working_set_size", ctypes.c_size_t),
            ("quota_peak_paged_pool_usage", ctypes.c_size_t),
            ("quota_paged_pool_usage", ctypes.c_size_t),
            ("quota_peak_non_paged_pool_usage", ctypes.c_size_t),
            ("quota_non_paged_pool_usage", ctypes.c_size_t),
            ("pagefile_usage", ctypes.c_size_t),
            ("peak_pagefile_usage", ctypes.c_size_t),
        )

    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    handle = ctypes.windll.kernel32.GetCurrentProcess()
    success = ctypes.windll.psapi.GetProcessMemoryInfo(
        handle,
        ctypes.byref(counters),
        counters.cb,
    )
    if not success:
        raise OSError("Process memory query failed.")
    return int(counters.working_set_size), int(counters.peak_working_set_size)


def _posix_memory() -> tuple[int, int]:
    import resource

    peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if sys.platform != "darwin":
        peak *= 1024
    resident = peak
    if sys.platform.startswith("linux"):
        with open("/proc/self/statm", encoding="ascii") as stream:
            resident_pages = int(stream.read().split()[1])
        resident = resident_pages * int(os.sysconf("SC_PAGE_SIZE"))
    return resident, peak


__all__ = ["StandardProcessMemoryProbe"]
