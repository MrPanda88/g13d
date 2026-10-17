"""Turn a stream of timestamped key events into macro steps (used by the GUI recorder).

The recorder is pure logic: feed it (key name, pressed, time) and read back steps.
Delays are recorded between consecutive events when `record_delays` is on, rounded to
`quantize_ms`, and ignored when shorter than `min_delay_ms`.
"""
from __future__ import annotations

import time

from g13d.config.macro import Step


class MacroRecorder:
    def __init__(self, record_delays: bool = True, min_delay_ms: int = 5, quantize_ms: int = 10):
        self.record_delays = record_delays
        self.min_delay_ms = min_delay_ms
        self.quantize_ms = max(1, quantize_ms)
        self.steps: list[Step] = []
        self._held: list[str] = []
        self._last: float | None = None
        self.recording = False

    def start(self) -> None:
        self.steps = []
        self._held = []
        self._last = None
        self.recording = True

    def event(self, key: str, pressed: bool, t: float | None = None) -> None:
        if not self.recording:
            return
        if pressed and key in self._held:
            return  # auto-repeat: not part of the macro, does not count as time either
        t = time.monotonic() if t is None else t
        if self._last is not None and self.record_delays:
            ms = int(round((t - self._last) * 1000 / self.quantize_ms) * self.quantize_ms)
            if ms >= self.min_delay_ms:
                self.steps.append(Step.delay(ms))
        self._last = t
        if pressed:
            self._held.append(key)
            self.steps.append(Step.press(key))
        else:
            if key in self._held:
                self._held.remove(key)
            self.steps.append(Step.release(key))

    def stop(self) -> list[Step]:
        """Stop recording; keys still held get a release step so the macro is balanced."""
        self.recording = False
        for key in reversed(self._held):
            self.steps.append(Step.release(key))
        self._held = []
        return self.steps

    @staticmethod
    def simplify(steps: list[Step]) -> list[Step]:
        """Merge press/release pairs with nothing in between into taps."""
        out: list[Step] = []
        i = 0
        while i < len(steps):
            s = steps[i]
            nxt = steps[i + 1] if i + 1 < len(steps) else None
            if s.kind == "press" and nxt is not None and nxt.kind == "release" and nxt.key == s.key:
                out.append(Step.tap(s.key))
                i += 2
                continue
            # press, short delay, release of the same key -> tap (drop the delay)
            nxt2 = steps[i + 2] if i + 2 < len(steps) else None
            if (s.kind == "press" and nxt is not None and nxt.kind == "delay" and nxt.ms <= 200
                    and nxt2 is not None and nxt2.kind == "release" and nxt2.key == s.key):
                out.append(Step.tap(s.key))
                i += 3
                continue
            out.append(s)
            i += 1
        return out
