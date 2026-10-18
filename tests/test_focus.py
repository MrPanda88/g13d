from g13d.daemon.focus import FocusInfo, process_name
from g13d.config.model import Profile, Settings
from g13d.config import tomlout
import tomllib, os


def test_identifiers_and_key():
    info = FocusInfo.from_dict({"wm_class": "steam_app_1234", "app_id": "steam_app_1234.desktop", "title": "Game", "pid": 0})
    assert info.key == "steam_app_1234"
    assert info.identifiers() == ["steam_app_1234", "Game"] or info.identifiers()[0] == "steam_app_1234"
    assert info.label == "steam_app_1234"
    assert not info.empty
    assert FocusInfo.from_dict({}).empty


def test_matching_rules():
    info = FocusInfo(wm_class="Firefox", wm_class_instance="Navigator", app_id="org.mozilla.firefox.desktop",
                     app_name="Firefox Web Browser", pid=0)
    assert info.matches("firefox")
    assert info.matches("org.mozilla.firefox")
    assert info.matches("navigator")
    assert info.matches("org.mozilla.*")
    assert info.matches("Firefox Web Browser")
    assert not info.matches("")
    assert not info.matches("chrome")


def test_process_name_of_self():
    assert process_name(os.getpid()).startswith("python")
    assert process_name(0) == ""
    assert process_name(2 ** 22 + 12345) == ""


def test_profile_app_and_setting_roundtrip():
    p = Profile("p", app="steam_app_*")
    back = Profile.from_toml(tomllib.loads(tomlout.dumps(p.to_toml())))
    assert back.app == "steam_app_*" and back == p
    assert "app" not in Profile("q").to_toml()
    s = Settings(auto_profiles=False)
    assert not Settings.from_toml(tomllib.loads(tomlout.dumps(s.to_toml()))).auto_profiles
    assert Settings.from_toml({}).auto_profiles
