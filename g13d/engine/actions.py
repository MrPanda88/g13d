"""Turn configured Actions into virtual input events or daemon commands."""
from __future__ import annotations

import logging
from typing import Protocol

from g13d.config.model import Action
from g13d.hw.names import key_code

from .uinput_out import VirtualInput

log = logging.getLogger(__name__)


class ActionContext(Protocol):
    """Daemon-side hooks for actions that are not plain key presses."""

    def set_mode(self, mode: int) -> None: ...
    def set_profile(self, name: str) -> None: ...
    def lcd_page(self, name: str) -> None: ...
    def run_macro(self, name: str, pressed: bool) -> None: ...


class ActionRunner:
    def __init__(self, vinput: VirtualInput, ctx: ActionContext):
        self._vi = vinput
        self._ctx = ctx

    def press(self, action: Action) -> None:
        match action.type:
            case "none":
                return
            case "key" | "combo":
                for k in action.keys:
                    self._vi.key(self._code(k), True)
            case "mouse":
                self._vi.key(self._code(action.name), True)
            case "macro":
                self._ctx.run_macro(action.name, True)
            case "mode":
                self._ctx.set_mode(action.number)
            case "profile":
                self._ctx.set_profile(action.name)
            case "lcd_page":
                self._ctx.lcd_page(action.name)
            case _:
                log.warning("unknown action type %r", action.type)

    def release(self, action: Action) -> None:
        match action.type:
            case "key" | "combo":
                for k in reversed(action.keys):
                    self._vi.key(self._code(k), False)
            case "mouse":
                self._vi.key(self._code(action.name), False)
            case "macro":
                self._ctx.run_macro(action.name, False)

    def release_all(self) -> None:
        self._vi.release_all()

    @staticmethod
    def _code(name: str) -> int:
        try:
            return key_code(name)
        except KeyError:
            log.warning("unknown key name %r, ignoring", name)
            return 0
