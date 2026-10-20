"""Macro data model and TOML (de)serialisation.

A macro is a list of steps played by the daemon's virtual input device:

    { press = "KEY_LEFTCTRL" }   hold a key down
    { release = "KEY_LEFTCTRL" } let it go
    { tap = "KEY_C" }            press + release
    { delay = 50 }               wait, milliseconds

repeat: "once" (play fully on press), "while_held" (loop until the G-key is released),
"toggle" (press starts the loop, next press stops it), "count" (play `count` times; a press while
it plays stops it). repeat_delay is the pause in milliseconds between two iterations.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .model import ConfigError

STEP_KINDS = ("press", "release", "tap", "delay")
REPEAT_MODES = ("once", "while_held", "toggle", "count")
MAX_COUNT = 9999


@dataclass(frozen=True)
class Step:
    kind: str
    key: str = ""
    ms: int = 0

    @classmethod
    def press(cls, key: str) -> Step:
        return cls("press", key)

    @classmethod
    def release(cls, key: str) -> Step:
        return cls("release", key)

    @classmethod
    def tap(cls, key: str) -> Step:
        return cls("tap", key)

    @classmethod
    def delay(cls, ms: int) -> Step:
        return cls("delay", ms=max(0, int(ms)))

    @classmethod
    def from_toml(cls, d) -> Step:
        if not isinstance(d, dict) or len(d) != 1:
            raise ConfigError(f"invalid macro step: {d!r}")
        (kind, arg), = d.items()
        if kind == "delay":
            if isinstance(arg, bool) or not isinstance(arg, (int, float)):
                raise ConfigError(f"delay must be a number of milliseconds: {d!r}")
            return cls.delay(int(arg))
        if kind in ("press", "release", "tap"):
            if not isinstance(arg, str) or not arg:
                raise ConfigError(f"{kind} needs a key name: {d!r}")
            return cls(kind, arg)
        raise ConfigError(f"unknown macro step kind {kind!r}")

    def to_toml(self) -> dict:
        return {"delay": self.ms} if self.kind == "delay" else {self.kind: self.key}

    def describe(self) -> str:
        if self.kind == "delay":
            return f"wait {self.ms} ms"
        sym = {"press": "↓", "release": "↑", "tap": "↓↑"}[self.kind]
        return f"{sym} {self.key.removeprefix('KEY_').removeprefix('BTN_')}"


@dataclass
class Macro:
    name: str
    steps: list[Step] = field(default_factory=list)
    repeat: str = "once"
    repeat_delay_ms: int = 0
    description: str = ""
    repeat_count: int = 2               # number of plays in "count" mode

    @classmethod
    def from_toml(cls, d: dict, fallback_name: str = "macro") -> Macro:
        repeat = str(d.get("repeat", "once"))
        if repeat not in REPEAT_MODES:
            raise ConfigError(f"repeat must be one of {REPEAT_MODES}, got {repeat!r}")
        steps_raw = d.get("steps", [])
        if not isinstance(steps_raw, list):
            raise ConfigError("steps must be an array")
        return cls(
            name=str(d.get("name", fallback_name)),
            steps=[Step.from_toml(s) for s in steps_raw],
            repeat=repeat,
            repeat_delay_ms=max(0, int(d.get("repeat_delay", 0))),
            description=str(d.get("description", "")),
            repeat_count=min(MAX_COUNT, max(1, int(d.get("count", 2)))),
        )

    def to_toml(self) -> dict:
        out: dict = {"name": self.name, "repeat": self.repeat}
        if self.repeat == "count":
            out["count"] = self.repeat_count
        if self.repeat_delay_ms:
            out["repeat_delay"] = self.repeat_delay_ms
        if self.description:
            out["description"] = self.description
        out["steps"] = [s.to_toml() for s in self.steps]
        return out

    @property
    def duration_ms(self) -> int:
        return sum(s.ms for s in self.steps if s.kind == "delay")

    def copy(self, name: str | None = None) -> Macro:
        return Macro(self.name if name is None else name, list(self.steps), self.repeat, self.repeat_delay_ms,
                     self.description, self.repeat_count)

    def keys_used(self) -> list[str]:
        seen: list[str] = []
        for s in self.steps:
            if s.key and s.key not in seen:
                seen.append(s.key)
        return seen


EXAMPLE_MACRO_TOML = '''# Example macro for g13d. Bind it in a profile with:  G9 = { macro = "example" }
# Steps: { press = "KEY_X" }  { release = "KEY_X" }  { tap = "KEY_X" }  { delay = 50 }  (ms)
# repeat: "once" | "while_held" | "toggle" | "count" (with count = N)   repeat_delay: pause between loops, ms
#
# Key names are physical positions (evdev): KEY_A is the key left of S, which types "q" on
# an AZERTY layout. This example only uses layout-independent keys. The GUI records keys by
# position for you, so you never have to think about it.
name = "example"
description = "Select the current line and copy it (Home, Shift+End, Ctrl+Insert)"
repeat = "once"
steps = [
  { tap = "KEY_HOME" },
  { press = "KEY_LEFTSHIFT" },
  { tap = "KEY_END" },
  { release = "KEY_LEFTSHIFT" },
  { delay = 30 },
  { press = "KEY_LEFTCTRL" },
  { tap = "KEY_INSERT" },
  { release = "KEY_LEFTCTRL" },
]
'''
