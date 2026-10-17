"""System page: CPU load and temperature, memory, network throughput."""
from __future__ import annotations

import time

import psutil

from g13d.lcd.fonts import font
from g13d.lcd.framebuffer import WIDTH

from .base import Page, bar

_TEMP_PREFS = (("k10temp", "Tctl"), ("k10temp", "Tdie"), ("coretemp", "Package id 0"), ("zenpower", "Tdie"), ("acpitz", None))


def human_rate(bps: float) -> str:
    for unit in ("B", "k", "M", "G"):
        if bps < 1000:
            return f"{bps:3.0f}{unit}" if unit == "B" else f"{bps:3.1f}{unit}" if bps < 10 else f"{bps:3.0f}{unit}"
        bps /= 1000
    return f"{bps:.0f}T"


def human_bytes(n: float) -> str:
    for unit in ("B", "K", "M", "G", "T"):
        if n < 1000:
            return f"{n:.0f}{unit}" if n >= 10 or unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.0f}P"


class SystemPage(Page):
    name = "system"
    title = "System"

    def __init__(self) -> None:
        self._net_prev: tuple[float, int, int] | None = None
        self._rx = self._tx = 0.0
        psutil.cpu_percent(None)  # prime the counter

    def _temperature(self) -> str:
        try:
            temps = psutil.sensors_temperatures()
        except (AttributeError, OSError):
            return ""
        for chip, label in _TEMP_PREFS:
            for entry in temps.get(chip, ()):
                if label is None or entry.label == label:
                    return f"{entry.current:.0f}°"
        for entries in temps.values():
            if entries:
                return f"{entries[0].current:.0f}°"
        return ""

    def _network(self) -> None:
        now = time.monotonic()
        rx = tx = 0
        for nic, c in psutil.net_io_counters(pernic=True).items():
            if nic == "lo":
                continue
            rx += c.bytes_recv
            tx += c.bytes_sent
        if self._net_prev is not None:
            dt = now - self._net_prev[0]
            if dt > 0:
                self._rx = (rx - self._net_prev[1]) / dt
                self._tx = (tx - self._net_prev[2]) / dt
        self._net_prev = (now, rx, tx)

    def render(self, draw, img, ctx) -> None:
        f = font(11, bold=False)
        cpu = psutil.cpu_percent(None)
        mem = psutil.virtual_memory()
        self._network()
        temp = self._temperature()

        draw.text((0, 0), f"CPU{cpu:4.0f}%", font=f, fill=1)
        bar(draw, 62, 2, 118, 11, cpu / 100)
        draw.text((124, 0), temp, font=f, fill=1)

        draw.text((0, 14), f"RAM{mem.percent:4.0f}%", font=f, fill=1)
        bar(draw, 62, 16, 118, 25, mem.percent / 100)
        draw.text((124, 14), human_bytes(mem.used), font=f, fill=1)

        draw.text((0, 29), f"NET  v {human_rate(self._rx).strip()}/s   ^ {human_rate(self._tx).strip()}/s", font=f, fill=1)
        draw.line((0, 27, WIDTH - 1, 27), fill=1)
