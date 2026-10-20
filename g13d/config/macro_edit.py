"""Pure helpers of the macro editor: matching press/release pairs, changing a key, undo/redo history."""
from __future__ import annotations

from g13d.hw.names import MODIFIERS

from .macro import Step


def partner(steps: list[Step], i: int) -> int | None:
    """Index of the release that ends the press at `i` (or of the press that the release at `i` ends)."""
    s = steps[i]
    if s.kind not in ("press", "release"):
        return None
    forward = s.kind == "press"
    depth = 0
    rng = range(i + 1, len(steps)) if forward else range(i - 1, -1, -1)
    for j in rng:
        t = steps[j]
        if t.key != s.key or t.kind == "tap" or t.kind == "delay":
            continue
        if t.kind == s.kind:
            depth += 1                 # nested press of the same key (rare): skip its own release
        elif depth:
            depth -= 1
        else:
            return j
    return None


def replace_key(steps: list[Step], i: int, key: str) -> list[Step]:
    """Steps with the key of step `i` changed, and the one of its press/release partner with it."""
    out = list(steps)
    for k in (i, partner(steps, i)):
        if k is not None and out[k].kind != "delay":
            out[k] = Step(out[k].kind, key)
    return out


class History:
    """Undo/redo of a step list. push() the steps *before* a change; changes with the same non-None `tag` in a
    row (e.g. one delay being spun) make a single undo entry."""

    def __init__(self, limit: int = 200):
        self._limit = limit
        self.reset()

    def reset(self) -> None:
        self._undo: list[tuple[Step, ...]] = []
        self._redo: list[tuple[Step, ...]] = []
        self._tag: object = None

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def push(self, steps: list[Step], tag: object = None) -> None:
        if tag is not None and tag == self._tag and self._undo:
            return
        self._undo.append(tuple(steps))
        del self._undo[:-self._limit]
        self._redo.clear()
        self._tag = tag

    def undo(self, current: list[Step]) -> list[Step] | None:
        if not self._undo:
            return None
        self._redo.append(tuple(current))
        self._tag = None
        return list(self._undo.pop())

    def redo(self, current: list[Step]) -> list[Step] | None:
        if not self._redo:
            return None
        self._undo.append(tuple(current))
        self._tag = None
        return list(self._redo.pop())


HOLD_MS = 400          # held this long, a key starts auto-repeating (or is held on purpose, e.g. walking in a game)


def merge_taps(steps: list[Step]) -> list[Step]:
    """Typing simplified: each key press becomes a tap where it was pressed, its release goes. Fast typing overlaps
    keys (T down, E down, T up…); tapping at the press keeps the order and the modifiers each key saw.

    Kept as press / release: modifiers (their hold is what makes the keys pressed meanwhile upper case, Ctrl+…),
    mouse buttons (holding one drags), keys held HOLD_MS or longer, and presses without a release. Waits left side
    by side once a release is gone are merged, so the presses keep their timing."""
    drop: set[int] = set()
    taps: set[int] = set()
    for i, s in enumerate(steps):
        if s.kind != "press" or s.key in MODIFIERS or s.key.startswith("BTN_"):
            continue
        j = partner(steps, i)
        if j is None or sum(steps[k].ms for k in range(i + 1, j) if steps[k].kind == "delay") >= HOLD_MS:
            continue
        taps.add(i)
        drop.add(j)
    out: list[Step] = []
    for i, s in enumerate(steps):
        if i in drop:
            continue
        s = Step.tap(s.key) if i in taps else s
        if s.kind == "delay" and out and out[-1].kind == "delay":
            out[-1] = Step.delay(out[-1].ms + s.ms)
        else:
            out.append(s)
    return out
