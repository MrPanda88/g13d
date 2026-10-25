"""Read/write g13d configuration under $XDG_CONFIG_HOME/g13d.

    config.toml        global settings
    state.json         runtime state written by the daemon (current profile / mode)
    profiles/*.toml    one file per profile (file stem == safe profile name), with its own assignment library
                       ([actions]) and macros ([macros.NAME])
    global/            what every profile gets on top of its own: actions.toml (assignment library) and
                       macros/*.toml (one file per macro)
    icons/             application icons found for the profiles (config/appicons.py)

Before 1.5 the assignment library (actions.toml) and the macros (macros/) were shared by all profiles:
migrate_shared() hands each profile the entries and macros it uses, once.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tomllib
from pathlib import Path

from . import tomlout
from .defaults import default_profile
from .library import ActionLibrary
from .macro import EXAMPLE_MACRO_TOML, Macro
from .model import MODES, ConfigError, Profile, Settings

log = logging.getLogger(__name__)


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / "g13d"


def safe_stem(name: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip()).strip("._")
    return stem or "profile"


class ConfigStore:
    def __init__(self, root: Path | None = None):
        self.root = root or config_dir()
        self.profiles_dir = self.root / "profiles"
        self.global_dir = self.root / "global"
        self.macros_dir = self.global_dir / "macros"
        self.icons_dir = self.root / "icons"

    # ---- settings -----------------------------------------------------
    def load_settings(self) -> Settings:
        p = self.root / "config.toml"
        if not p.exists():
            return Settings()
        with p.open("rb") as f:
            return Settings.from_toml(tomllib.load(f))

    def save_settings(self, s: Settings) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        _atomic_write(self.root / "config.toml", tomlout.dumps(s.to_toml()))

    # ---- runtime state ------------------------------------------------
    def load_state(self) -> dict:
        p = self.root / "state.json"
        try:
            return json.loads(p.read_text())
        except (OSError, ValueError):
            return {}

    def save_state(self, state: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        _atomic_write(self.root / "state.json", json.dumps(state, indent=1))

    # ---- profiles -----------------------------------------------------
    def ensure_defaults(self) -> None:
        """Create the directory tree and a Default profile (with the example macro) on first run."""
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self.macros_dir.mkdir(parents=True, exist_ok=True)
        if not any(self.profiles_dir.glob("*.toml")):
            prof = default_profile()
            example = Macro.from_toml(tomllib.loads(EXAMPLE_MACRO_TOML))
            prof.macros[example.name] = example
            self.save_profile(prof)
            log.info("created default profile in %s", self.profiles_dir)
        if not (self.root / "config.toml").exists():
            self.save_settings(Settings())
        self.migrate_shared()

    # ---- pre-1.5 shared library and macros ----------------------------------
    def _legacy_files(self) -> list[Path]:
        return [p for p in (self.root / "actions.toml", self.root / "macros") if p.exists()]

    def migrate_shared(self) -> bool:
        """Pre-1.5 configuration: give each profile the library entries and macros its keys use, the macros no
        profile uses go to the default profile; nothing is left global. The old files are kept, renamed *.pre-1.5."""
        legacy = self._legacy_files()
        if not legacy:
            return False
        old_root = ConfigStore(self.root)
        old_root.macros_dir = self.root / "macros"
        library = self.load_library(self.root / "actions.toml")
        macros = old_root.load_macros()
        profiles = self.load_profiles()
        used: set[str] = set()
        for prof in profiles.values():
            actions = [a for m in MODES for a in prof.modes.get(m, {}).values()]
            for action in actions:
                entry = library.find(action)
                if entry is not None and prof.library.find(action) is None:
                    prof.library.add(action, entry.label)
                if action.type == "macro" and action.name in macros and action.name not in prof.macros:
                    prof.macros[action.name] = macros[action.name].copy()
                    used.add(action.name)
        unused = [n for n in macros if n not in used]
        if unused and profiles:
            settings = self.load_settings()
            home = profiles.get(settings.default_profile) or profiles.get("Default") or next(iter(profiles.values()))
            for n in unused:
                home.macros.setdefault(n, macros[n].copy())
            log.info("macros used by no profile moved to %r: %s", home.name, ", ".join(unused))
        for prof in profiles.values():
            self.save_profile(prof)
        for p in legacy:
            target = p.with_name(p.name + ".pre-1.5")
            if target.exists():
                shutil.rmtree(target) if target.is_dir() else target.unlink()
            p.rename(target)
        log.info("assignment library and macros now belong to each profile (old files kept as *.pre-1.5)")
        return True

    def load_profiles(self) -> dict[str, Profile]:
        profiles: dict[str, Profile] = {}
        for p in sorted(self.profiles_dir.glob("*.toml")):
            try:
                with p.open("rb") as f:
                    prof = Profile.from_toml(tomllib.load(f), fallback_name=p.stem)
            except (tomllib.TOMLDecodeError, ConfigError, OSError) as e:
                log.error("skipping profile %s: %s", p.name, e)
                continue
            if prof.name in profiles:
                log.warning("duplicate profile name %r in %s, keeping the first one", prof.name, p.name)
                continue
            profiles[prof.name] = prof
        return profiles

    def profile_path(self, name: str) -> Path:
        return self.profiles_dir / f"{safe_stem(name)}.toml"

    def save_profile(self, prof: Profile) -> Path:
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        path = self.profile_path(prof.name)
        _atomic_write(path, tomlout.dumps(prof.to_toml()))
        return path

    def delete_profile(self, name: str) -> None:
        path = self.profile_path(name)
        if path.exists():
            path.unlink()


    # ---- global assignment library -------------------------------------
    def load_library(self, path: Path | None = None) -> ActionLibrary:
        p = path or self.global_dir / "actions.toml"
        if not p.exists():
            return ActionLibrary()
        try:
            with p.open("rb") as f:
                return ActionLibrary.from_toml(tomllib.load(f))
        except (tomllib.TOMLDecodeError, ConfigError, OSError) as e:
            log.error("ignoring %s: %s", p, e)
            return ActionLibrary()

    def save_library(self, lib: ActionLibrary) -> None:
        self.global_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write(self.global_dir / "actions.toml", tomlout.dumps(lib.to_toml()))

    # ---- global macros ------------------------------------------------
    def load_macros(self) -> dict[str, Macro]:
        macros: dict[str, Macro] = {}
        if not self.macros_dir.is_dir():
            return macros
        for p in sorted(self.macros_dir.glob("*.toml")):
            try:
                with p.open("rb") as f:
                    m = Macro.from_toml(tomllib.load(f), fallback_name=p.stem)
            except (tomllib.TOMLDecodeError, ConfigError, OSError) as e:
                log.error("skipping macro %s: %s", p.name, e)
                continue
            if m.name in macros:
                log.warning("duplicate macro name %r in %s, keeping the first one", m.name, p.name)
                continue
            macros[m.name] = m
        return macros

    def macro_path(self, name: str) -> Path:
        return self.macros_dir / f"{safe_stem(name)}.toml"

    def save_macro(self, macro: Macro) -> Path:
        self.macros_dir.mkdir(parents=True, exist_ok=True)
        path = self.macro_path(macro.name)
        _atomic_write(path, tomlout.dumps(macro.to_toml()))
        return path

    def delete_macro(self, name: str) -> None:
        path = self.macro_path(name)
        if path.exists():
            path.unlink()


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)
