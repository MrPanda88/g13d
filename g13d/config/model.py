"""Configuration data model: profiles, modes, actions, stick settings."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .library import ActionLibrary
    from .macro import Macro

G_KEYS = tuple(f"G{i}" for i in range(1, 23))
LCD_KEYS = ("LCD1", "LCD2", "LCD3", "LCD4", "LCD_MENU")
STICK_DIRS = ("STICK_UP", "STICK_DOWN", "STICK_LEFT", "STICK_RIGHT")
STICK_BUTTONS = ("STICK_PRESS", "STICK_BTN_LEFT", "STICK_BTN_DOWN")
M_KEYS = ("M1", "M2", "M3", "MR")
BINDABLE = G_KEYS + LCD_KEYS + STICK_DIRS + STICK_BUTTONS + ("LIGHT",)
MODES = (1, 2, 3)
STICK_MODES = ("keys", "mouse", "scroll", "passthrough")
ACTION_TYPES = ("none", "key", "combo", "macro", "mouse", "mode", "profile", "lcd_page")
GUI_LAYOUTS = ("lgs", "gtk")
LIBRARY_SORTS = ("added", "name", "type")
MACRO_STYLES = ("flow", "icons", "timeline")
DEFAULT_LCD_PAGES = ("status", "clock", "system", "media")
_LAYOUT_ALIASES = {"classic": "gtk", "device": "lgs"}


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Action:
    """What a bindable control does.

    type      meaning                      payload
    none      nothing                      -
    key       press one keyboard key       keys = ("KEY_A",)
    combo     press several keys together  keys = ("KEY_LEFTCTRL", "KEY_C")
    macro     play a macro                 name = macro name
    mouse     press a mouse button         name = "BTN_LEFT" | "BTN_RIGHT" | "BTN_MIDDLE" | ...
    mode      switch to M-mode             number = 1..3
    profile   switch profile               name = profile name
    lcd_page  show LCD page                name = page name | "next" | "prev"
    """

    type: str = "none"
    keys: tuple[str, ...] = ()
    name: str = ""
    number: int = 0

    # ---- constructors -------------------------------------------------
    @classmethod
    def none(cls) -> Action:
        return cls()

    @classmethod
    def key(cls, key: str) -> Action:
        return cls("key", (key,))

    @classmethod
    def combo(cls, *keys: str) -> Action:
        return cls("combo", tuple(keys))

    @classmethod
    def macro(cls, name: str) -> Action:
        return cls("macro", name=name)

    @classmethod
    def mouse(cls, button: str) -> Action:
        return cls("mouse", name=button)

    @classmethod
    def mode(cls, n: int) -> Action:
        return cls("mode", number=n)

    @classmethod
    def profile(cls, name: str) -> Action:
        return cls("profile", name=name)

    @classmethod
    def lcd_page(cls, name: str) -> Action:
        return cls("lcd_page", name=name)

    # ---- (de)serialisation --------------------------------------------
    @classmethod
    def from_toml(cls, value) -> Action:
        if value is None or value == "none" or value == "":
            return cls.none()
        if isinstance(value, str):
            return cls.key(value)
        if not isinstance(value, dict) or len(value) != 1:
            raise ConfigError(f"invalid action: {value!r}")
        (kind, arg), = value.items()
        match kind:
            case "key":
                return cls.key(str(arg))
            case "combo":
                if not isinstance(arg, list) or not arg:
                    raise ConfigError(f"combo needs a non-empty list: {value!r}")
                return cls.combo(*map(str, arg))
            case "macro":
                return cls.macro(str(arg))
            case "mouse":
                return cls.mouse(str(arg))
            case "mode":
                if arg not in MODES:
                    raise ConfigError(f"mode must be 1, 2 or 3: {value!r}")
                return cls.mode(int(arg))
            case "profile":
                return cls.profile(str(arg))
            case "lcd_page":
                return cls.lcd_page(str(arg))
        raise ConfigError(f"unknown action kind {kind!r}")

    def to_toml(self):
        match self.type:
            case "none":
                return "none"
            case "key":
                return self.keys[0]
            case "combo":
                return {"combo": list(self.keys)}
            case "macro":
                return {"macro": self.name}
            case "mouse":
                return {"mouse": self.name}
            case "mode":
                return {"mode": self.number}
            case "profile":
                return {"profile": self.name}
            case "lcd_page":
                return {"lcd_page": self.name}
        raise ConfigError(f"unknown action type {self.type!r}")

    def describe(self) -> str:
        """Short human label (evdev names, layout-agnostic)."""
        match self.type:
            case "none":
                return "—"
            case "key":
                return _short(self.keys[0])
            case "combo":
                return "+".join(_short(k) for k in self.keys)
            case "macro":
                return f"⏵ {self.name}"
            case "mouse":
                return _short(self.name) if self.name in _labels() else "Mouse " + _short(self.name)
            case "mode":
                return f"M{self.number}"
            case "profile":
                return f"→ {self.name}"
            case "lcd_page":
                return f"LCD {self.name}"
        return self.type


def _labels() -> dict[str, str]:
    from g13d.hw.names import KEY_LABELS  # local import: hw.names needs evdev, the model stays importable without it
    return KEY_LABELS


def _short(evdev_name: str) -> str:
    if evdev_name in _labels():
        return _labels()[evdev_name]
    for prefix in ("KEY_", "BTN_"):
        if evdev_name.startswith(prefix):
            return evdev_name[len(prefix):].replace("_", " ").title()
    return evdev_name


@dataclass
class StickConfig:
    mode: str = "keys"          # keys | mouse | scroll | passthrough
    deadzone: float = 0.25      # 0..1, fraction of full deflection
    mouse_speed: float = 800.0  # pixels per second at full deflection
    scroll_speed: float = 8.0   # wheel ticks per second at full deflection
    invert_y: bool = False

    @classmethod
    def from_toml(cls, d: dict | None) -> StickConfig:
        d = d or {}
        cfg = cls(
            mode=str(d.get("mode", "keys")),
            deadzone=float(d.get("deadzone", 0.25)),
            mouse_speed=float(d.get("mouse_speed", 800.0)),
            scroll_speed=float(d.get("scroll_speed", 8.0)),
            invert_y=bool(d.get("invert_y", False)),
        )
        if cfg.mode not in STICK_MODES:
            raise ConfigError(f"stick.mode must be one of {STICK_MODES}")
        cfg.deadzone = min(max(cfg.deadzone, 0.0), 0.95)
        return cfg

    def to_toml(self) -> dict:
        return {
            "mode": self.mode,
            "deadzone": self.deadzone,
            "mouse_speed": self.mouse_speed,
            "scroll_speed": self.scroll_speed,
            "invert_y": self.invert_y,
        }


Bindings = dict[str, Action]


def _new_library() -> ActionLibrary:
    from .library import ActionLibrary  # local import: library.py and macro.py import this module
    return ActionLibrary()


@dataclass
class Profile:
    """One profile file: its bindings and its own assignment library and macros (a profile's `library` and `macros`
    belong to it alone; the global ones, in the ConfigStore, are added to every profile's)."""
    name: str
    backlight: tuple[int, int, int] = (0, 0, 255)
    icon: str = ""              # GUI only: image file path or themed icon name shown on the profile tile
    app: str = ""               # window class / app id / process the profile is for (auto-switch), "" = none
    stick: StickConfig = field(default_factory=StickConfig)
    modes: dict[int, Bindings] = field(default_factory=lambda: {m: {} for m in MODES})
    library: ActionLibrary = field(default_factory=_new_library)
    macros: dict[str, Macro] = field(default_factory=dict)
    # [lcd] pages of profiles written before 1.2 (pages are global now): read once for migration, never written
    legacy_lcd_pages: list[str] | None = field(default=None, compare=False, repr=False)

    def binding(self, mode: int, control: str) -> Action:
        return self.modes.get(mode, {}).get(control, Action.none())

    def set_binding(self, mode: int, control: str, action: Action) -> None:
        if control not in BINDABLE:
            raise ConfigError(f"{control!r} is not bindable")
        if action.type == "none":
            self.modes.setdefault(mode, {}).pop(control, None)
        else:
            self.modes.setdefault(mode, {})[control] = action

    @classmethod
    def from_toml(cls, d: dict, fallback_name: str = "Unnamed") -> Profile:
        bl = d.get("backlight", [0, 0, 255])
        if not (isinstance(bl, list) and len(bl) == 3):
            raise ConfigError("backlight must be [r, g, b]")
        backlight = tuple(min(max(int(c), 0), 255) for c in bl)
        lcd = d.get("lcd", {}) or {}
        modes: dict[int, Bindings] = {}
        for m in MODES:
            table = d.get(f"m{m}", {}) or {}
            if not isinstance(table, dict):
                raise ConfigError(f"[m{m}] must be a table")
            bindings: Bindings = {}
            for control, raw in table.items():
                if control not in BINDABLE:
                    raise ConfigError(f"[m{m}] {control!r} is not a bindable control")
                act = Action.from_toml(raw)
                if act.type != "none":
                    bindings[control] = act
            modes[m] = bindings
        from .library import ActionLibrary
        from .macro import Macro
        raw_macros = d.get("macros", {}) or {}
        if not isinstance(raw_macros, dict):
            raise ConfigError("[macros] must be a table of macros")
        macros = {}
        for mname, raw in raw_macros.items():
            if not isinstance(raw, dict):
                raise ConfigError(f"[macros.{mname}] must be a table")
            macros[str(mname)] = Macro.from_toml({**raw, "name": str(mname)})
        return cls(
            name=str(d.get("name", fallback_name)),
            backlight=backlight,  # type: ignore[arg-type]
            icon=str(d.get("icon", "")),
            app=str(d.get("app", "")),
            stick=StickConfig.from_toml(d.get("stick")),
            modes=modes,
            library=ActionLibrary.from_toml({"actions": d.get("actions", {})}),
            macros=macros,
            legacy_lcd_pages=[str(p) for p in lcd["pages"]] if isinstance(lcd.get("pages"), list) else None,
        )

    def to_toml(self) -> dict:
        out: dict = {
            "name": self.name,
            "backlight": list(self.backlight),
            **({"icon": self.icon} if self.icon else {}),
            **({"app": self.app} if self.app else {}),
            "stick": self.stick.to_toml(),
        }
        for m in MODES:
            out[f"m{m}"] = {c: a.to_toml() for c, a in sorted(self.modes.get(m, {}).items(), key=_control_order)}
        if self.library.entries:
            out.update(self.library.to_toml())
        if self.macros:
            out["macros"] = {name: {k: v for k, v in m.to_toml().items() if k != "name"}
                             for name, m in sorted(self.macros.items(), key=lambda kv: kv[0].casefold())}
        return out

    def copy(self, new_name: str) -> Profile:
        """A duplicate with its own copy of everything, assignment library and macros included."""
        return replace(self, name=new_name, stick=replace(self.stick),
                       modes={m: dict(b) for m, b in self.modes.items()},
                       library=self.library.copy(), macros={n: m.copy() for n, m in self.macros.items()})


def order_profiles(names, order: list[str]) -> list[str]:
    """`names` in the user's order: the ones listed in `order` first (in that order), the rest alphabetically."""
    names = set(names)
    out = [n for n in order if n in names]
    out += sorted(names - set(out))
    return out


def _control_order(item):
    control = item[0]
    return (BINDABLE.index(control) if control in BINDABLE else 999, control)


@dataclass
class Settings:
    """Global daemon settings (~/.config/g13d/config.toml).

    default_profile: profile loaded when the daemon starts; empty = restore the last used one.
    auto_profiles: switch to the profile linked to the focused application (needs the GNOME Shell extension).
    lcd_pages / lcd_options: the LCD pages shown (same whatever the profile) and their settings ([lcd]).
    gui_layout: how g13-gui arranges its window ([gui] layout): "lgs" (device picture, the default) or "gtk" (classic widgets).
    gui_library_sort: order of the assignments panel ([gui] library_sort): "added", "name" or "type".
    gui_macro_style: how the macro editor draws the steps ([gui] macro_style): "flow", "icons" or "timeline".
    """
    default_profile: str = ""
    lcd_enabled: bool = True
    log_level: str = "INFO"
    auto_profiles: bool = True          # switch to a profile when its application gets the focus
    profile_order: list[str] = field(default_factory=list)   # display / cycling order; unknown names go last, A-Z
    lcd_pages: list[str] = field(default_factory=lambda: list(DEFAULT_LCD_PAGES))
    lcd_options: dict[str, str] = field(default_factory=dict)
    gui_layout: str = "lgs"
    gui_library_sort: str = "added"
    gui_macro_style: str = "flow"
    lcd_configured: bool = field(default=True, compare=False)   # False: the file had no [lcd] table yet

    @classmethod
    def from_toml(cls, d: dict) -> Settings:
        g = d.get("general", d) or {}
        gui = d.get("gui", {}) or {}
        lcd = d.get("lcd")
        layout = str(gui.get("layout", "lgs"))
        layout = _LAYOUT_ALIASES.get(layout, layout)
        sort = str(gui.get("library_sort", "added"))
        macro_style = str(gui.get("macro_style", "flow"))
        pages = (lcd or {}).get("pages")
        return cls(
            default_profile=str(g.get("default_profile", "")),
            lcd_enabled=bool(g.get("lcd_enabled", True)),
            log_level=str(g.get("log_level", "INFO")).upper(),
            auto_profiles=bool(g.get("auto_profiles", True)),
            profile_order=[str(x) for x in g.get("profile_order", []) or []],
            lcd_pages=[str(x) for x in pages] if isinstance(pages, list) and pages else list(DEFAULT_LCD_PAGES),
            lcd_options={str(k): str(v) for k, v in ((lcd or {}).get("options", {}) or {}).items()},
            gui_layout=layout if layout in GUI_LAYOUTS else "lgs",
            gui_library_sort=sort if sort in LIBRARY_SORTS else "added",
            gui_macro_style=macro_style if macro_style in MACRO_STYLES else "flow",
            lcd_configured=isinstance(lcd, dict),
        )

    def to_toml(self) -> dict:
        return {"general": {"default_profile": self.default_profile,
                            "lcd_enabled": self.lcd_enabled,
                            "log_level": self.log_level,
                            "auto_profiles": self.auto_profiles,
                            "profile_order": list(self.profile_order)},
                "lcd": {"pages": list(self.lcd_pages), **({"options": dict(self.lcd_options)} if self.lcd_options else {})},
                "gui": {"layout": self.gui_layout, "library_sort": self.gui_library_sort,
                        "macro_style": self.gui_macro_style}}
