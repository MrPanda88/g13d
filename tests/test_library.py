import tomllib

from g13d.config import tomlout
from g13d.config.library import ActionLibrary
from g13d.config.loader import ConfigStore
from g13d.config.model import Action, Profile


def test_add_dedups_and_labels():
    lib = ActionLibrary()
    assert lib.add(Action.combo("KEY_LEFTCTRL", "KEY_C")).label == "Ctrl+C"
    assert lib.add(Action.combo("KEY_LEFTCTRL", "KEY_C")) is None
    assert lib.add(Action.none()) is None
    assert lib.add(Action.macro("m")) is None          # macros are listed live, not stored
    assert lib.add(Action.key("KEY_A"), "Fire").label == "Fire"
    assert lib.add(Action.key("KEY_B"), "Fire").label == "Fire (2)"
    assert len(lib.entries) == 3


def test_rename_remove_replace():
    lib = ActionLibrary()
    a = Action.key("KEY_A")
    lib.add(a)
    assert lib.rename(a, "Jump")
    assert lib.find(a).label == "Jump"
    assert not lib.rename(a, "  ")
    assert lib.replace(a, Action.key("KEY_SPACE"))
    assert lib.find(Action.key("KEY_SPACE")).label == "Jump"
    assert not lib.replace(Action.key("KEY_SPACE"), Action.none())
    assert lib.remove(Action.key("KEY_SPACE"))
    assert not lib.remove(Action.key("KEY_SPACE"))
    assert lib.entries == []


def test_absorb_profiles():
    p1 = Profile("one")
    p1.set_binding(1, "G1", Action.key("KEY_HOME"))
    p1.set_binding(2, "G1", Action.key("KEY_END"))
    p1.set_binding(1, "G2", Action.macro("x"))
    p2 = Profile("two")
    p2.set_binding(1, "G1", Action.key("KEY_HOME"))
    p2.set_binding(3, "G5", Action.profile("one"))
    lib = ActionLibrary()
    assert lib.absorb([p1, p2]) == 3
    assert lib.absorb([p1, p2]) == 0
    assert {e.action for e in lib.entries} == {Action.key("KEY_HOME"), Action.key("KEY_END"), Action.profile("one")}


def test_retarget():
    lib = ActionLibrary()
    lib.add(Action.profile("old"))
    lib.add(Action.profile("other"), "Go other")
    assert lib.retarget("profile", "old", "new")
    assert lib.find(Action.profile("new")).label == "→ new"
    assert lib.retarget("profile", "other", None)
    assert lib.find(Action.profile("other")) is None
    assert not lib.retarget("profile", "nope", None)


def test_toml_roundtrip():
    lib = ActionLibrary()
    lib.add(Action.combo("KEY_LEFTCTRL", "KEY_C"), "Copy & paste <ctrl>")
    lib.add(Action.key("KEY_ENTER"))
    lib.add(Action.mouse("BTN_LEFT"))
    lib.add(Action.mode(2))
    lib.add(Action.lcd_page("next"))
    text = tomlout.dumps(lib.to_toml())
    back = ActionLibrary.from_toml(tomllib.loads(text))
    assert back == lib


def test_from_toml_skips_junk():
    lib = ActionLibrary.from_toml({"actions": {"a": "KEY_A", "b": "KEY_A", "m": {"macro": "x"}, "n": "none"}})
    assert [e.label for e in lib.entries] == ["a"]


def test_store_roundtrip(tmp_path):
    store = ConfigStore(root=tmp_path)
    assert store.load_library().entries == []
    lib = ActionLibrary()
    lib.add(Action.key("KEY_F1"))
    store.save_library(lib)
    assert store.load_library() == lib
    (tmp_path / "global" / "actions.toml").write_text("not toml [[[")
    assert store.load_library().entries == []
