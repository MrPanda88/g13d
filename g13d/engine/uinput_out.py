"""One virtual input device (keyboard + mouse) through /dev/uinput.

Works on Wayland and X11 alike because events enter the kernel like any physical device.
Button ranges reserved for joysticks, gamepads and touch devices are deliberately not
advertised: libinput would otherwise ignore the device or misclassify it.
"""
from __future__ import annotations

import logging

import evdev
from evdev import ecodes as e

log = logging.getLogger(__name__)

DEVICE_NAME = "g13d virtual input"


def _key_capabilities() -> list[int]:
    codes: list[int] = []
    codes.extend(range(e.KEY_ESC, 0x100))            # keyboard proper
    codes.extend(range(e.BTN_LEFT, e.BTN_TASK + 1))  # mouse buttons 0x110..0x117
    codes.extend(range(0x160, 0x290))                # consumer / multimedia KEY_* (stops before KEY_MACRO1)
    return [c for c in codes if c in e.KEY or c in e.BTN]


class VirtualInput:
    def __init__(self) -> None:
        caps = {
            e.EV_KEY: _key_capabilities(),
            e.EV_REL: [e.REL_X, e.REL_Y, e.REL_WHEEL, e.REL_HWHEEL],
        }
        self._ui = evdev.UInput(caps, name=DEVICE_NAME, vendor=0x1209, product=0x0013, version=1,
                                bustype=e.BUS_VIRTUAL)
        self._held: set[int] = set()
        log.info("virtual input device created (%s)", self._ui.devnode or DEVICE_NAME)

    def close(self) -> None:
        self.release_all()
        self._ui.close()

    # ---- keys -----------------------------------------------------------
    def key(self, code: int, pressed: bool) -> None:
        self._ui.write(e.EV_KEY, code, 1 if pressed else 0)
        self._ui.syn()
        if pressed:
            self._held.add(code)
        else:
            self._held.discard(code)

    def tap(self, code: int) -> None:
        self._ui.write(e.EV_KEY, code, 1)
        self._ui.syn()
        self._ui.write(e.EV_KEY, code, 0)
        self._ui.syn()

    def release_all(self) -> None:
        for code in list(self._held):
            try:
                self.key(code, False)
            except OSError:
                pass
        self._held.clear()

    @property
    def held(self) -> frozenset[int]:
        return frozenset(self._held)

    # ---- pointer --------------------------------------------------------
    def move(self, dx: int, dy: int) -> None:
        if dx:
            self._ui.write(e.EV_REL, e.REL_X, dx)
        if dy:
            self._ui.write(e.EV_REL, e.REL_Y, dy)
        if dx or dy:
            self._ui.syn()

    def scroll(self, vertical: int = 0, horizontal: int = 0) -> None:
        if vertical:
            self._ui.write(e.EV_REL, e.REL_WHEEL, vertical)
        if horizontal:
            self._ui.write(e.EV_REL, e.REL_HWHEEL, horizontal)
        if vertical or horizontal:
            self._ui.syn()
