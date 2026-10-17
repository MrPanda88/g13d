"""Engine tests with a fake virtual input device (no /dev/uinput needed)."""
import asyncio

from g13d.config.model import Action, StickConfig
from g13d.engine.actions import ActionRunner
from g13d.engine.stick import Stick
from g13d.hw.names import key_code


class FakeInput:
    def __init__(self):
        self.events = []
        self._held = set()

    def key(self, code, pressed):
        self.events.append(("key", code, pressed))
        (self._held.add if pressed else self._held.discard)(code)

    def move(self, dx, dy):
        self.events.append(("move", dx, dy))

    def scroll(self, v=0, h=0):
        self.events.append(("scroll", v, h))

    def release_all(self):
        for c in list(self._held):
            self.key(c, False)


class FakeCtx:
    def __init__(self):
        self.calls = []

    def set_mode(self, m): self.calls.append(("mode", m))
    def set_profile(self, n): self.calls.append(("profile", n))
    def lcd_page(self, n): self.calls.append(("lcd", n))
    def run_macro(self, n, p): self.calls.append(("macro", n, p))


def test_combo_press_release_order():
    vi, ctx = FakeInput(), FakeCtx()
    r = ActionRunner(vi, ctx)
    a = Action.combo("KEY_LEFTCTRL", "KEY_C")
    r.press(a); r.release(a)
    assert vi.events == [
        ("key", key_code("KEY_LEFTCTRL"), True), ("key", key_code("KEY_C"), True),
        ("key", key_code("KEY_C"), False), ("key", key_code("KEY_LEFTCTRL"), False),
    ]


def test_daemon_actions_go_to_context():
    vi, ctx = FakeInput(), FakeCtx()
    r = ActionRunner(vi, ctx)
    r.press(Action.mode(2)); r.press(Action.profile("P")); r.press(Action.lcd_page("next"))
    r.press(Action.macro("m")); r.release(Action.macro("m"))
    assert ctx.calls == [("mode", 2), ("profile", "P"), ("lcd", "next"), ("macro", "m", True), ("macro", "m", False)]
    assert vi.events == []


def test_stick_keys_mode():
    async def run():
        vi, ctx = FakeInput(), FakeCtx()
        bindings = {"STICK_UP": Action.key("KEY_UP"), "STICK_RIGHT": Action.key("KEY_RIGHT")}
        st = Stick(ActionRunner(vi, ctx), vi, lambda n: bindings.get(n, Action.none()))
        st.configure(StickConfig(mode="keys", deadzone=0.25))
        st.update(128, 128)
        assert vi.events == []
        st.update(250, 10)           # right + up
        assert ("key", key_code("KEY_RIGHT"), True) in vi.events
        assert ("key", key_code("KEY_UP"), True) in vi.events
        st.update(128, 128)
        assert ("key", key_code("KEY_RIGHT"), False) in vi.events
        assert ("key", key_code("KEY_UP"), False) in vi.events
        st.stop()
    asyncio.run(run())


def test_stick_mouse_mode_moves():
    async def run():
        vi, ctx = FakeInput(), FakeCtx()
        st = Stick(ActionRunner(vi, ctx), vi, lambda n: Action.none())
        st.configure(StickConfig(mode="mouse", deadzone=0.1, mouse_speed=1200))
        st.update(255, 128)
        await asyncio.sleep(0.2)
        st.stop()
        moves = [e for e in vi.events if e[0] == "move"]
        assert moves and all(dx > 0 and dy == 0 for _, dx, dy in moves)
    asyncio.run(run())
