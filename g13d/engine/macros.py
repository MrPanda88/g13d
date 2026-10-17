"""Macro playback: one asyncio task per running macro, keys released on cancel."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from g13d.config.macro import Macro
from g13d.hw.names import key_code

log = logging.getLogger(__name__)

MacroLookup = Callable[[str], Macro | None]


class MacroPlayer:
    def __init__(self, vinput, lookup: MacroLookup, on_change: Callable[[], None] | None = None):
        self._vi = vinput
        self._lookup = lookup
        self._on_change = on_change
        self._tasks: dict[str, asyncio.Task] = {}

    # ---- public -------------------------------------------------------------
    @property
    def active(self) -> list[str]:
        return sorted(self._tasks)

    def trigger(self, name: str, pressed: bool) -> None:
        """Called on press/release of a control bound to the macro."""
        macro = self._lookup(name)
        if macro is None:
            if pressed:
                log.warning("macro %r not found", name)
            return
        running = name in self._tasks and not self._tasks[name].done()
        if pressed:
            if macro.repeat == "toggle" and running:
                self.stop(name)
                return
            self.start(macro)
        elif macro.repeat == "while_held" and running:
            self.stop(name)

    def start(self, macro: Macro) -> None:
        self.stop(macro.name)
        self._tasks[macro.name] = asyncio.get_running_loop().create_task(self._run(macro))
        log.info("macro %r started (%s)", macro.name, macro.repeat)
        self._notify()

    def stop(self, name: str) -> None:
        task = self._tasks.get(name)
        if task is not None and not task.done():
            task.cancel()

    def stop_all(self) -> None:
        for name in list(self._tasks):
            self.stop(name)

    # ---- internals ----------------------------------------------------------
    def _notify(self) -> None:
        if self._on_change:
            try:
                self._on_change()
            except Exception:  # noqa: BLE001
                log.exception("macro change callback failed")

    async def _run(self, macro: Macro) -> None:
        held: set[int] = set()
        try:
            while True:
                for step in macro.steps:
                    if step.kind == "delay":
                        if step.ms:
                            await asyncio.sleep(step.ms / 1000)
                        continue
                    code = self._code(step.key)
                    if not code:
                        continue
                    if step.kind == "press":
                        self._vi.key(code, True)
                        held.add(code)
                    elif step.kind == "release":
                        self._vi.key(code, False)
                        held.discard(code)
                    elif step.kind == "tap":
                        self._vi.key(code, True)
                        self._vi.key(code, False)
                        held.discard(code)
                    await asyncio.sleep(0)  # keep the loop responsive even without delays
                if macro.repeat == "once":
                    break
                await asyncio.sleep(max(macro.repeat_delay_ms, 1) / 1000)
        except asyncio.CancelledError:
            log.info("macro %r stopped", macro.name)
        else:
            log.info("macro %r finished", macro.name)
        finally:
            for code in held:
                try:
                    self._vi.key(code, False)
                except OSError:
                    pass
            if self._tasks.get(macro.name) is asyncio.current_task():
                del self._tasks[macro.name]
            self._notify()

    @staticmethod
    def _code(name: str) -> int:
        try:
            return key_code(name)
        except KeyError:
            log.warning("macro step: unknown key %r", name)
            return 0
