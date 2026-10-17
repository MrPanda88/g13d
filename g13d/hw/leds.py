"""M1/M2/M3/MR LEDs and RGB backlight through the kernel LED class (sysfs)."""
from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)


class Leds:
    def __init__(self, leds: dict[str, Path]):
        self._leds = leds
        self._warned: set[str] = set()

    def _write(self, led: str, attr: str, value: str) -> bool:
        path = self._leds.get(led)
        if path is None:
            return False
        try:
            (path / attr).write_text(value)
            return True
        except PermissionError:
            if led not in self._warned:
                self._warned.add(led)
                log.warning("cannot write %s/%s: permission denied (udev rule 70-g13d.rules not installed?)", path, attr)
        except OSError as exc:
            log.warning("cannot write %s/%s: %s", path, attr, exc)
        return False

    def set_mode(self, mode: int) -> None:
        for n in (1, 2, 3):
            self._write(f"m{n}", "brightness", "1" if n == mode else "0")

    def set_record(self, on: bool) -> None:
        self._write("mr", "brightness", "1" if on else "0")

    def set_backlight(self, rgb: tuple[int, int, int], brightness: int = 255) -> None:
        r, g, b = (min(max(int(c), 0), 255) for c in rgb)
        self._write("backlight", "multi_intensity", f"{r} {g} {b}")
        self._write("backlight", "brightness", str(min(max(brightness, 0), 255)))

    def all_off(self) -> None:
        for n in ("m1", "m2", "m3", "mr"):
            self._write(n, "brightness", "0")
