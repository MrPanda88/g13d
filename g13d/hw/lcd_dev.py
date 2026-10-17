"""Push framebuffers to the G13 LCD through its hidraw node (output report 3)."""
from __future__ import annotations

import logging
import os

from g13d.lcd.framebuffer import REPORT_SIZE

log = logging.getLogger(__name__)


class LcdDevice:
    def __init__(self, hidraw_path: str):
        self._path = hidraw_path
        self._fd: int | None = None

    def open(self) -> None:
        self._fd = os.open(self._path, os.O_WRONLY)

    def close(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            finally:
                self._fd = None

    def write(self, report: bytes) -> bool:
        if self._fd is None:
            return False
        if len(report) != REPORT_SIZE:
            raise ValueError(f"LCD report must be {REPORT_SIZE} bytes, got {len(report)}")
        try:
            os.write(self._fd, report)
            return True
        except OSError as exc:
            log.warning("LCD write failed on %s: %s", self._path, exc)
            return False
