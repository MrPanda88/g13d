"""The assignment library: every action the user has bound or saved, ready to be dropped on a key.

Stored in ~/.config/g13d/actions.toml as a table of label -> action:

    [actions]
    "Ctrl+C" = { combo = ["KEY_LEFTCTRL", "KEY_C"] }
    Enter = "KEY_ENTER"

Macros are not stored here: the GUI lists them straight from the macro files.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from .model import MODES, Action, ConfigError, Profile

# Actions that only make sense as live references, never as library entries
_SKIP = ("none", "macro")


@dataclass
class LibraryEntry:
    label: str
    action: Action


@dataclass
class ActionLibrary:
    entries: list[LibraryEntry] = field(default_factory=list)

    # ---- queries ---------------------------------------------------------------------
    def find(self, action: Action) -> LibraryEntry | None:
        return next((e for e in self.entries if e.action == action), None)

    def labels(self) -> set[str]:
        return {e.label for e in self.entries}

    # ---- edits ------------------------------------------------------------------------
    def add(self, action: Action, label: str = "") -> LibraryEntry | None:
        """Add `action` unless an identical one is already listed. Returns the new entry, or None."""
        if action.type in _SKIP or self.find(action) is not None:
            return None
        entry = LibraryEntry(self._unique(label.strip() or action.describe()), action)
        self.entries.append(entry)
        return entry

    def remove(self, action: Action) -> bool:
        before = len(self.entries)
        self.entries = [e for e in self.entries if e.action != action]
        return len(self.entries) != before

    def rename(self, action: Action, label: str) -> bool:
        entry = self.find(action)
        label = label.strip()
        if entry is None or not label or entry.label == label:
            return False
        entry.label = self._unique(label)
        return True

    def replace(self, old: Action, new: Action) -> bool:
        """Change what an entry does (its label is kept). Refused if `new` is already listed elsewhere."""
        entry = self.find(old)
        if entry is None or new.type in _SKIP or (new != old and self.find(new) is not None):
            return False
        entry.action = new
        return True

    def absorb(self, profiles: Iterable[Profile]) -> int:
        """Add every binding of every profile that is not listed yet. Returns how many were added."""
        added = 0
        for prof in profiles:
            for mode in MODES:
                for action in prof.modes.get(mode, {}).values():
                    if self.add(action) is not None:
                        added += 1
        return added

    def retarget(self, kind: str, old: str, new: str | None) -> bool:
        """A profile was renamed (new) or deleted (None): fix or drop the entries that pointed at it."""
        touched = False
        for entry in list(self.entries):
            if entry.action.type == kind and entry.action.name == old:
                touched = True
                if new is None:
                    self.entries.remove(entry)
                else:
                    replacement = Action.profile(new) if kind == "profile" else Action.macro(new)
                    if entry.label == entry.action.describe():
                        entry.label = replacement.describe()
                    entry.action = replacement
        return touched

    def _unique(self, label: str) -> str:
        taken = self.labels()
        candidate, n = label, 2
        while candidate in taken:
            candidate = f"{label} ({n})"
            n += 1
        return candidate

    # ---- (de)serialisation ------------------------------------------------------------
    @classmethod
    def from_toml(cls, d: dict) -> ActionLibrary:
        table = d.get("actions", {}) or {}
        if not isinstance(table, dict):
            raise ConfigError("[actions] must be a table")
        lib = cls()
        for label, raw in table.items():
            action = Action.from_toml(raw)
            if action.type in _SKIP or lib.find(action) is not None:
                continue
            lib.entries.append(LibraryEntry(lib._unique(str(label)), action))
        return lib

    def to_toml(self) -> dict:
        return {"actions": {e.label: e.action.to_toml() for e in self.entries}}
