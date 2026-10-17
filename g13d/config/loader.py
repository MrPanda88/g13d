"""Read/write g13d configuration under $XDG_CONFIG_HOME/g13d.

    config.toml        global settings
    state.json         runtime state written by the daemon (current profile / mode)
    profiles/*.toml    one file per profile (file stem == safe profile name)
    macros/*.toml      one file per macro (used from milestone M3 on)
"""
from __future__ import annotations

import json
import logging
import os
import re
import tomllib
from pathlib import Path

from . import tomlout
from .defaults import default_profile
from .macro import EXAMPLE_MACRO_TOML, Macro
from .model import ConfigError, Profile, Settings

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
        self.macros_dir = self.root / "macros"

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
        """Create the directory tree and a Default profile on first run."""
        self.profiles_dir.mkdir(parents=True, exist_ok=True)
        self.macros_dir.mkdir(parents=True, exist_ok=True)
        if not any(self.profiles_dir.glob("*.toml")):
            self.save_profile(default_profile())
            log.info("created default profile in %s", self.profiles_dir)
        if not any(self.macros_dir.glob("*.toml")):
            _atomic_write(self.macros_dir / "example.toml", EXAMPLE_MACRO_TOML)
        if not (self.root / "config.toml").exists():
            self.save_settings(Settings())

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


    # ---- macros -------------------------------------------------------
    def load_macros(self) -> dict[str, Macro]:
        macros: dict[str, Macro] = {}
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
