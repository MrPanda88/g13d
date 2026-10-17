"""Thumbstick processing: arrow-style keys, pointer, scroll wheel or passthrough."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from g13d.config.model import Action, StickConfig

from .actions import ActionRunner
from .uinput_out import VirtualInput

log = logging.getLogger(__name__)

RATE_HZ = 60
BindingLookup = Callable[[str], Action]  # control name -> current action


class Stick:
    def __init__(self, runner: ActionRunner, vinput: VirtualInput, lookup: BindingLookup):
        self._runner = runner
        self._vi = vinput
        self._lookup = lookup
        self._cfg = StickConfig()
        self._nx = self._ny = 0.0
        self._dirs: dict[str, Action] = {}   # currently pressed direction -> action used
        self._acc_x = self._acc_y = 0.0
        self._task: asyncio.Task | None = None

    # ---- configuration --------------------------------------------------
    def configure(self, cfg: StickConfig) -> None:
        self.reset()
        self._cfg = cfg
        if cfg.mode in ("mouse", "scroll"):
            if self._task is None or self._task.done():
                self._task = asyncio.get_running_loop().create_task(self._periodic())
        elif self._task is not None:
            self._task.cancel()
            self._task = None

    def stop(self) -> None:
        self.reset()
        if self._task is not None:
            self._task.cancel()
            self._task = None

    def reset(self) -> None:
        """Release held direction keys (mode/profile switch, device loss)."""
        for action in self._dirs.values():
            self._runner.release(action)
        self._dirs.clear()
        self._nx = self._ny = 0.0
        self._acc_x = self._acc_y = 0.0

    # ---- input ------------------------------------------------------------
    def update(self, raw_x: int, raw_y: int) -> None:
        nx = (raw_x - 127.5) / 127.5
        ny = (raw_y - 127.5) / 127.5
        if self._cfg.invert_y:
            ny = -ny
        self._nx = max(-1.0, min(1.0, nx))
        self._ny = max(-1.0, min(1.0, ny))
        if self._cfg.mode == "keys":
            self._update_keys()

    def _update_keys(self) -> None:
        dz = self._cfg.deadzone
        wanted = {
            "STICK_LEFT": self._nx < -dz,
            "STICK_RIGHT": self._nx > dz,
            "STICK_UP": self._ny < -dz,
            "STICK_DOWN": self._ny > dz,
        }
        for name, on in wanted.items():
            held = name in self._dirs
            if on and not held:
                action = self._lookup(name)
                self._dirs[name] = action
                self._runner.press(action)
            elif not on and held:
                self._runner.release(self._dirs.pop(name))

    # ---- pointer / scroll -------------------------------------------------
    def _scaled(self, v: float) -> float:
        dz = self._cfg.deadzone
        m = abs(v)
        if m <= dz:
            return 0.0
        m = (m - dz) / (1.0 - dz)
        m = m * m  # quadratic curve: precise near centre, fast at the edge
        return m if v > 0 else -m

    async def _periodic(self) -> None:
        dt = 1.0 / RATE_HZ
        try:
            while True:
                await asyncio.sleep(dt)
                sx, sy = self._scaled(self._nx), self._scaled(self._ny)
                if not sx and not sy:
                    self._acc_x = self._acc_y = 0.0
                    continue
                if self._cfg.mode == "mouse":
                    self._acc_x += sx * self._cfg.mouse_speed * dt
                    self._acc_y += sy * self._cfg.mouse_speed * dt
                    dx, dy = int(self._acc_x), int(self._acc_y)
                    self._acc_x -= dx
                    self._acc_y -= dy
                    self._vi.move(dx, dy)
                elif self._cfg.mode == "scroll":
                    self._acc_y += -sy * self._cfg.scroll_speed * dt   # push up = scroll up
                    self._acc_x += sx * self._cfg.scroll_speed * dt
                    v, h = int(self._acc_y), int(self._acc_x)
                    self._acc_y -= v
                    self._acc_x -= h
                    self._vi.scroll(v, h)
        except asyncio.CancelledError:
            pass
