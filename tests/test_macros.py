import asyncio
import tomllib

import pytest

from g13d.config import tomlout
from g13d.config.loader import ConfigStore
from g13d.config.macro import EXAMPLE_MACRO_TOML, Macro, Step
from g13d.config.model import ConfigError
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
    assert "example" in store.load_macros()
    store.save_macro(Macro("Hello World", [Step.tap("KEY_H")]))
    assert store.macro_path("Hello World").name == "Hello_World.toml"
    assert set(store.load_macros()) == {"example", "Hello World"}
    store.delete_macro("Hello World")
    assert set(store.load_macros()) == {"example"}


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
