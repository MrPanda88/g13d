"""What one profile sees: its own macros and assignment library plus the global ones (its own win a name clash).

The GUI edits macros through a ProfileScope, which saves each one where it lives: in the profile's file, or in the
global macros folder. A macro created from a profile belongs to that profile.
"""
from __future__ import annotations

from collections.abc import Callable

from .loader import ConfigStore
from .macro import Macro
from .model import Profile


class ProfileScope:
    def __init__(self, store: ConfigStore, profile: Callable[[], Profile | None]):
        self._store = store
        self._profile = profile

    @property
    def profile(self) -> Profile | None:
        return self._profile()

    # ---- macros ------------------------------------------------------------------------
    def load_macros(self) -> dict[str, Macro]:
        prof = self.profile
        return {**self._store.load_macros(), **(prof.macros if prof else {})}

    def is_global_macro(self, name: str) -> bool:
        prof = self.profile
        return (prof is None or name not in prof.macros) and name in self._store.load_macros()

    def save_macro(self, macro: Macro) -> None:
        prof = self.profile
        if self.is_global_macro(macro.name) or prof is None:
            self._store.save_macro(macro)
        else:
            prof.macros[macro.name] = macro
            self._store.save_profile(prof)

    def delete_macro(self, name: str) -> None:
        prof = self.profile
        if prof is not None and name in prof.macros:
            del prof.macros[name]
            self._store.save_profile(prof)
        else:
            self._store.delete_macro(name)

    def rename_macro(self, old: str, macro: Macro) -> None:
        """`macro` (named `old` until now) carries its new name; it stays where it was."""
        prof = self.profile
        if prof is not None and old in prof.macros:
            prof.macros = {(macro.name if n == old else n): (macro if n == old else m) for n, m in prof.macros.items()}
            self._store.save_profile(prof)
        else:
            self._store.delete_macro(old)
            self._store.save_macro(macro)
