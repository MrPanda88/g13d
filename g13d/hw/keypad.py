"""Read the two G13 evdev devices (keypad + thumbstick) with exclusive grab."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

import evdev
from evdev import ecodes as e

from .discover import G13Paths
from .names import KEYPAD_CODE_TO_NAME, STICK_CODE_TO_NAME

log = logging.getLogger(__name__)

KeyCallback = Callable[[str, bool], None]         # (control name, pressed)
StickCallback = Callable[[int, int], None]        # (x, y) raw 0..255


class DeviceLost(Exception):
    pass


class Keypad:
    def __init__(self, paths: G13Paths, on_key: KeyCallback, on_stick: StickCallback, grab_stick: bool = True):
        self._paths = paths
        self._on_key = on_key
        self._on_stick = on_stick
        self._passthrough = not grab_stick
        self._keypad: evdev.InputDevice | None = None
        self._stick: evdev.InputDevice | None = None
        self._x = self._y = 128

    def open(self) -> None:
        assert self._paths.keypad_event and self._paths.stick_event
        self._keypad = evdev.InputDevice(self._paths.keypad_event)
        self._keypad.grab()
        self._stick = evdev.InputDevice(self._paths.stick_event)
        if not self._passthrough:
            self._stick.grab()
        log.info("opened %s (%s) + %s%s", self._keypad.path, self._keypad.name, self._stick.path,
                 " (stick passthrough)" if self._passthrough else "")

    def set_passthrough(self, passthrough: bool) -> None:
        """Passthrough: leave the stick to games (no grab, events ignored)."""
        if passthrough == self._passthrough:
            return
        self._passthrough = passthrough
        if self._stick is None:
            return
        try:
            if passthrough:
                self._stick.ungrab()
            else:
                self._stick.grab()
        except OSError as exc:
            log.warning("stick grab change failed: %s", exc)

    def close(self) -> None:
        for dev in (self._keypad, self._stick):
            if dev is None:
                continue
            try:
                dev.ungrab()
            except OSError:
                pass
            try:
                dev.close()
            except OSError:
                pass
        self._keypad = self._stick = None

    async def run(self) -> None:
        """Dispatch events until the device disappears; raises DeviceLost."""
        tasks = [asyncio.create_task(self._read_keypad())]
        if self._stick is not None:
            tasks.append(asyncio.create_task(self._read_stick()))
        try:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
            for t in pending:
                t.cancel()
            for t in done:
                exc = t.exception()
                if exc is not None:
                    raise exc
        finally:
            for t in tasks:
                t.cancel()

    async def _read_keypad(self) -> None:
        assert self._keypad is not None
        try:
            async for ev in self._keypad.async_read_loop():
                if ev.type != e.EV_KEY or ev.value == 2:
                    continue
                name = KEYPAD_CODE_TO_NAME.get(ev.code)
                if name is None:
                    log.debug("unknown keypad code %d", ev.code)
                    continue
                self._on_key(name, ev.value == 1)
        except OSError as exc:
            raise DeviceLost(f"keypad: {exc}") from exc

    async def _read_stick(self) -> None:
        assert self._stick is not None
        try:
            async for ev in self._stick.async_read_loop():
                if self._passthrough:
                    continue
                if ev.type == e.EV_ABS:
                    if ev.code == e.ABS_X:
                        self._x = ev.value
                    elif ev.code == e.ABS_Y:
                        self._y = ev.value
                    else:
                        continue
                    self._on_stick(self._x, self._y)
                elif ev.type == e.EV_KEY and ev.value != 2:
                    name = STICK_CODE_TO_NAME.get(ev.code)
                    if name:
                        self._on_key(name, ev.value == 1)
        except OSError as exc:
            raise DeviceLost(f"stick: {exc}") from exc
