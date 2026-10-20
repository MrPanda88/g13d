import tomllib

import pytest

from g13d.config import tomlout
from g13d.config.defaults import default_profile
from g13d.config.loader import ConfigStore
from g13d.config.model import Action, ConfigError, Profile, StickConfig


def test_action_parsing():
    assert Action.from_toml("KEY_A") == Action.key("KEY_A")
    assert Action.from_toml({"combo": ["KEY_LEFTCTRL", "KEY_C"]}) == Action.combo("KEY_LEFTCTRL", "KEY_C")
    assert Action.from_toml({"mode": 2}) == Action.mode(2)
    assert Action.from_toml({"macro": "x"}).type == "macro"
    assert Action.from_toml("none").type == "none"
    assert Action.from_toml(None).type == "none"
    with pytest.raises(ConfigError):
        Action.from_toml({"mode": 4})
    with pytest.raises(ConfigError):
        Action.from_toml({"combo": []})
    with pytest.raises(ConfigError):
        Action.from_toml({"bogus": 1})


def test_action_toml_roundtrip():
    for a in (Action.key("KEY_A"), Action.combo("KEY_LEFTSHIFT", "KEY_F1"), Action.macro("m"),
              Action.mouse("BTN_LEFT"), Action.mode(3), Action.profile("P"), Action.lcd_page("next")):
        assert Action.from_toml(a.to_toml()) == a


def test_profile_roundtrip():
    p = default_profile("Test")
    p.set_binding(2, "G5", Action.combo("KEY_LEFTCTRL", "KEY_Z"))
    p.set_binding(3, "G1", Action.none())
    p.stick = StickConfig(mode="mouse", deadzone=0.3, mouse_speed=500)
    text = tomlout.dumps(p.to_toml())
    back = Profile.from_toml(tomllib.loads(text))
    assert back == p


def test_profile_rejects_unknown_control():
    with pytest.raises(ConfigError):
        Profile.from_toml({"name": "x", "m1": {"G99": "KEY_A"}})


def test_tomlout_escapes():
    data = {"name": 'He said "hi"\\', "t": {"k": [1, 2.5, True, "s"], "d": {"a": 1}}, "weird key!": 3}
    assert tomllib.loads(tomlout.dumps(data)) == data


def test_settings_default_profile_roundtrip(tmp_path):
    from g13d.config.model import Settings
    store = ConfigStore(root=tmp_path)
    assert store.load_settings().default_profile == ""
    store.save_settings(Settings(default_profile="Gaming"))
    assert store.load_settings().default_profile == "Gaming"


def test_store_roundtrip(tmp_path):
    store = ConfigStore(root=tmp_path)
    store.ensure_defaults()
    profiles = store.load_profiles()
    assert "Default" in profiles
    p = profiles["Default"].copy("Gaming")
    p.backlight = (255, 0, 0)
    store.save_profile(p)
    again = store.load_profiles()
    assert set(again) == {"Default", "Gaming"}
    assert again["Gaming"].backlight == (255, 0, 0)
    store.save_state({"profile": "Gaming", "mode": 2})
    assert store.load_state() == {"profile": "Gaming", "mode": 2}


def test_profile_icon_roundtrip():
    p = Profile("p", icon="/tmp/x.png")
    d = p.to_toml()
    assert d["icon"] == "/tmp/x.png"
    assert Profile.from_toml(tomllib.loads(tomlout.dumps(d))) == p
    assert "icon" not in Profile("q").to_toml()
    assert p.copy("r").icon == "/tmp/x.png"


def test_settings_gui_layout():
    from g13d.config.model import Settings
    assert Settings().gui_layout == "lgs"
    s = Settings.from_toml(tomllib.loads(tomlout.dumps(Settings(gui_layout="lgs").to_toml())))
    assert s.gui_layout == "lgs"
    assert Settings.from_toml({"gui": {"layout": "bogus"}}).gui_layout == "lgs"
    assert Settings.from_toml({"gui": {"layout": "device"}}).gui_layout == "lgs"     # pre-1.1 names
    assert Settings.from_toml({"gui": {"layout": "classic"}}).gui_layout == "gtk"
    assert Settings.from_toml({"general": {"default_profile": "x"}}).default_profile == "x"


def test_settings_lcd_roundtrip_and_legacy_profile_pages():
    from g13d.config.model import Settings
    s = Settings(lcd_pages=["clock", "profiles"], lcd_options={"clock_style": "numbers"})
    back = Settings.from_toml(tomllib.loads(tomlout.dumps(s.to_toml())))
    assert back == s and back.lcd_configured
    fresh = Settings.from_toml({"general": {}})
    assert fresh.lcd_pages == ["status", "clock", "system", "media"] and not fresh.lcd_configured
    assert "options" not in Settings().to_toml()["lcd"]
    # profiles written before 1.2 carried [lcd] pages: read for migration, never written back
    p = Profile.from_toml({"name": "old", "lcd": {"pages": ["clock", "text"]}})
    assert p.legacy_lcd_pages == ["clock", "text"]
    assert "lcd" not in p.to_toml()
    assert Profile.from_toml({"name": "new"}).legacy_lcd_pages is None
    assert p.copy("c") == Profile("c")


def test_settings_library_sort():
    from g13d.config.model import Settings
    assert Settings.from_toml({"gui": {"library_sort": "type"}}).gui_library_sort == "type"
    assert Settings.from_toml({"gui": {"library_sort": "zzz"}}).gui_library_sort == "added"


def test_order_profiles():
    from g13d.config.model import Settings, order_profiles
    assert order_profiles({"b", "a", "c"}, ["c", "zzz", "a"]) == ["c", "a", "b"]
    assert order_profiles(["b", "a"], []) == ["a", "b"]
    s = Settings(profile_order=["x", "y"])
    assert Settings.from_toml(tomllib.loads(tomlout.dumps(s.to_toml()))).profile_order == ["x", "y"]
