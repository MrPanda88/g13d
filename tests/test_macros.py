import asyncio
import tomllib

import pytest

from g13d.config import tomlout
from g13d.config.loader import ConfigStore
from g13d.config.macro import EXAMPLE_MACRO_TOML, Macro, Step
from g13d.config.model import Action, ConfigError, Profile
from g13d.engine.macros import MacroPlayer
from g13d.engine.recorder import MacroRecorder
from g13d.hw.names import key_code

from .test_engine import FakeInput

CTRL, A, C = key_code("KEY_LEFTCTRL"), key_code("KEY_A"), key_code("KEY_C")


def test_macro_toml_roundtrip():
    m = Macro("m", [Step.press("KEY_LEFTCTRL"), Step.delay(30), Step.tap("KEY_C"), Step.release("KEY_LEFTCTRL")],
              repeat="toggle", repeat_delay_ms=100, description="d")
    text = tomlout.dumps(m.to_toml())
    assert Macro.from_toml(tomllib.loads(text)) == m
    assert "steps = [\n" in text


def test_example_macro_parses():
    m = Macro.from_toml(tomllib.loads(EXAMPLE_MACRO_TOML))
    assert m.name == "example" and len(m.steps) == 8 and m.duration_ms == 30
    assert m.keys_used() == ["KEY_HOME", "KEY_LEFTSHIFT", "KEY_END", "KEY_LEFTCTRL", "KEY_INSERT"]


def test_macro_validation():
    with pytest.raises(ConfigError):
        Macro.from_toml({"repeat": "forever"})
    with pytest.raises(ConfigError):
        Step.from_toml({"delay": "soon"})
    with pytest.raises(ConfigError):
        Step.from_toml({"press": ""})
    with pytest.raises(ConfigError):
        Step.from_toml({"press": "KEY_A", "tap": "KEY_B"})


def test_store_macros(tmp_path):
    store = ConfigStore(root=tmp_path)
    store.ensure_defaults()
    # the example ships inside the default profile, nothing is global at first
    assert "example" in store.load_profiles()["Default"].macros
    assert store.load_macros() == {}
    store.save_macro(Macro("Hello World", [Step.tap("KEY_H")]))
    assert store.macro_path("Hello World") == tmp_path / "global" / "macros" / "Hello_World.toml"
    assert set(store.load_macros()) == {"Hello World"}
    store.delete_macro("Hello World")
    assert store.load_macros() == {}


def test_profile_macros_and_library_roundtrip(tmp_path):
    store = ConfigStore(root=tmp_path)
    prof = Profile("P")
    prof.macros["Craft it"] = Macro("Craft it", [Step.tap("KEY_KP0"), Step.delay(20)], "toggle", 500, "LGS")
    prof.library.add(Action.key("KEY_Q"), "Heal")
    prof.set_binding(1, "G1", Action.macro("Craft it"))
    store.save_profile(prof)
    back = store.load_profiles()["P"]
    assert back.macros == prof.macros and back.library == prof.library
    assert back.binding(1, "G1") == Action.macro("Craft it")


def test_profile_copy_owns_its_items():
    prof = Profile("P")
    prof.macros["m"] = Macro("m", [Step.tap("KEY_A")])
    prof.library.add(Action.key("KEY_Q"), "Heal")
    dup = prof.copy("Q")
    assert dup.macros == prof.macros and dup.library == prof.library
    dup.macros["m"].steps.append(Step.delay(5))
    dup.library.rename(Action.key("KEY_Q"), "Soin")
    assert prof.macros["m"].steps == [Step.tap("KEY_A")]
    assert prof.library.entries[0].label == "Heal"


def test_migrate_shared_library_and_macros(tmp_path):
    store = ConfigStore(root=tmp_path)
    a, b = Profile("A"), Profile("B")
    a.set_binding(1, "G1", Action.macro("Hello"))
    a.set_binding(1, "G2", Action.key("KEY_Q"))
    b.set_binding(1, "G1", Action.key("KEY_Q"))
    b.set_binding(1, "G2", Action.key("KEY_F1"))
    store.save_profile(a)
    store.save_profile(b)
    (tmp_path / "actions.toml").write_text('[actions]\nHeal = "KEY_Q"\nUnused = "KEY_F5"\n')
    old = tmp_path / "macros"
    old.mkdir()
    (old / "Hello.toml").write_text('name = "Hello"\nsteps = [{ tap = "KEY_H" }]\n')
    (old / "Spare.toml").write_text('name = "Spare"\nsteps = []\n')
    (tmp_path / "config.toml").write_text('[general]\ndefault_profile = "B"\n')
    store.ensure_defaults()
    profs = store.load_profiles()
    assert set(profs) == {"A", "B"}
    assert set(profs["A"].macros) == {"Hello"}
    assert set(profs["B"].macros) == {"Spare"}              # used by nobody: the default profile keeps it
    assert [e.label for e in profs["A"].library.entries] == ["Heal"]
    assert [e.label for e in profs["B"].library.entries] == ["Heal"]
    assert store.load_macros() == {} and store.load_library().entries == []
    assert (tmp_path / "actions.toml.pre-1.5").exists() and (tmp_path / "macros.pre-1.5").is_dir()
    assert not store.migrate_shared()                       # once


def test_scope_saves_where_the_macro_lives(tmp_path):
    from g13d.config.scope import ProfileScope
    store = ConfigStore(root=tmp_path)
    prof = Profile("P")
    store.save_profile(prof)
    store.save_macro(Macro("Global", [Step.tap("KEY_F1")]))
    scope = ProfileScope(store, lambda: prof)
    scope.save_macro(Macro("Mine", [Step.tap("KEY_A")]))
    assert "Mine" in store.load_profiles()["P"].macros and "Mine" not in store.load_macros()
    assert set(scope.load_macros()) == {"Global", "Mine"} and scope.is_global_macro("Global")
    g = scope.load_macros()["Global"]
    g.steps.append(Step.delay(10))
    scope.save_macro(g)
    assert store.load_macros()["Global"].steps[-1] == Step.delay(10)
    m = scope.load_macros()["Mine"]
    m.name = "Renamed"
    scope.rename_macro("Mine", m)
    assert set(store.load_profiles()["P"].macros) == {"Renamed"}
    scope.delete_macro("Renamed")
    assert store.load_profiles()["P"].macros == {}


def _player(vi, macros):
    return MacroPlayer(vi, lambda n: macros.get(n))


def test_play_once_releases_held_keys():
    async def run():
        vi = FakeInput()
        m = Macro("m", [Step.press("KEY_LEFTCTRL"), Step.tap("KEY_C")])  # forgets to release ctrl
        p = _player(vi, {"m": m})
        p.trigger("m", True)
        await asyncio.sleep(0.05)
        assert vi.events == [("key", CTRL, True), ("key", C, True), ("key", C, False), ("key", CTRL, False)]
        assert p.active == []
    asyncio.run(run())


def test_while_held_loops_until_release():
    async def run():
        vi = FakeInput()
        m = Macro("m", [Step.tap("KEY_A"), Step.delay(10)], repeat="while_held")
        p = _player(vi, {"m": m})
        p.trigger("m", True)
        await asyncio.sleep(0.08)
        assert p.active == ["m"]
        p.trigger("m", False)
        await asyncio.sleep(0.02)
        taps = [e for e in vi.events if e == ("key", A, True)]
        assert 3 <= len(taps) <= 10
        assert p.active == []
    asyncio.run(run())


def test_while_held_finishes_current_pass():
    async def run():
        vi = FakeInput()
        m = Macro("m", [Step.tap("KEY_A"), Step.delay(40), Step.tap("KEY_C")], repeat="while_held")
        p = _player(vi, {"m": m})
        p.trigger("m", True)
        await asyncio.sleep(0.005)
        p.trigger("m", False)          # released early: the pass must still complete
        await asyncio.sleep(0.08)
        assert ("key", C, True) in vi.events
        assert p.active == []
        assert sum(1 for e in vi.events if e == ("key", A, True)) == 1
    asyncio.run(run())


def test_toggle_starts_and_stops():
    async def run():
        vi = FakeInput()
        m = Macro("m", [Step.tap("KEY_A"), Step.delay(10)], repeat="toggle")
        p = _player(vi, {"m": m})
        p.trigger("m", True); p.trigger("m", False)
        await asyncio.sleep(0.05)
        assert p.active == ["m"]
        p.trigger("m", True)
        await asyncio.sleep(0.02)
        assert p.active == []
    asyncio.run(run())


def test_unknown_macro_is_harmless():
    async def run():
        p = _player(FakeInput(), {})
        p.trigger("nope", True)
        p.trigger("nope", False)
    asyncio.run(run())


def test_recorder_delays_and_balance():
    r = MacroRecorder(min_delay_ms=5, quantize_ms=10)
    r.start()
    r.event("KEY_LEFTSHIFT", True, 1.000)
    r.event("KEY_A", True, 1.052)
    r.event("KEY_A", True, 1.080)   # auto-repeat ignored
    r.event("KEY_A", False, 1.101)
    steps = r.stop()                # shift still held -> released
    assert steps == [Step.press("KEY_LEFTSHIFT"), Step.delay(50), Step.press("KEY_A"), Step.delay(50),
                     Step.release("KEY_A"), Step.release("KEY_LEFTSHIFT")]
    simple = MacroRecorder.simplify(steps)
    assert simple == [Step.press("KEY_LEFTSHIFT"), Step.delay(50), Step.tap("KEY_A"), Step.release("KEY_LEFTSHIFT")]


def test_recorder_without_delays():
    r = MacroRecorder(record_delays=False)
    r.start()
    r.event("KEY_A", True, 0); r.event("KEY_A", False, 5)
    assert MacroRecorder.simplify(r.stop()) == [Step.tap("KEY_A")]


def test_count_mode_roundtrip_and_validation():
    m = Macro("m", [Step.tap("KEY_A")], repeat="count", repeat_count=5)
    text = tomlout.dumps(m.to_toml())
    assert "count = 5" in text
    assert Macro.from_toml(tomllib.loads(text)) == m
    assert Macro.from_toml({"repeat": "count", "count": 0}).repeat_count == 1
    assert "count" not in Macro("m", repeat="once", repeat_count=5).to_toml()


def test_count_plays_n_times():
    async def run():
        vi = FakeInput()
        m = Macro("m", [Step.tap("KEY_A")], repeat="count", repeat_count=3)
        p = _player(vi, {"m": m})
        p.trigger("m", True); p.trigger("m", False)
        await asyncio.sleep(0.05)
        assert sum(1 for e in vi.events if e == ("key", A, True)) == 3
        assert p.active == []
    asyncio.run(run())


def test_count_stopped_by_second_press():
    async def run():
        vi = FakeInput()
        m = Macro("m", [Step.tap("KEY_A"), Step.delay(10)], repeat="count", repeat_count=1000)
        p = _player(vi, {"m": m})
        p.trigger("m", True); p.trigger("m", False)
        await asyncio.sleep(0.05)
        assert p.active == ["m"]
        p.trigger("m", True)
        await asyncio.sleep(0.02)
        assert p.active == []
        assert sum(1 for e in vi.events if e == ("key", A, True)) < 1000
    asyncio.run(run())
