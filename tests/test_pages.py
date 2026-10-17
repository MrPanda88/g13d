"""Render every built-in LCD page off-device."""
from PIL import ImageDraw

from g13d.lcd.framebuffer import encode, new_image
from g13d.lcd.pages import BUILTIN, make_pages
from g13d.lcd.pages.base import fit, marquee
from g13d.lcd.pages.text import TextPage, wrap
from g13d.lcd.fonts import font


class Ctx:
    profile_name = "A rather long profile name that will not fit"
    mode = 3
    recording = False
    connected = True
    calls = []

    def set_mode(self, m): self.calls.append(("mode", m))
    def cycle_profile(self, d): self.calls.append(("cycle", d))


def _render(page):
    img = new_image()
    page.render(ImageDraw.Draw(img), img, Ctx())
    return encode(img)


def test_all_pages_render():
    for name, cls in BUILTIN.items():
        page = cls()
        if isinstance(page, TextPage):
            page.text = "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor"
        data = _render(page)
        assert len(data) == 992
        if name != "blank":
            assert any(data[32:]), f"page {name} rendered nothing"


def test_make_pages_filters_and_dedups():
    assert [p.name for p in make_pages(["clock", "bogus", "clock", "status"])] == ["clock", "status"]
    assert [p.name for p in make_pages([])] == ["status"]


def test_status_buttons():
    ctx = Ctx(); ctx.calls = []
    page = BUILTIN["status"]()
    for i in (1, 2, 3, 4):
        assert page.button(i, ctx)
    assert ctx.calls == [("mode", 1), ("mode", 2), ("mode", 3), ("cycle", 1)]


def test_text_helpers():
    img = new_image(); draw = ImageDraw.Draw(img); f = font(13)
    assert fit(draw, "short", f, 160) == "short"
    assert fit(draw, "x" * 80, f, 160).endswith("…")
    assert draw.textlength(fit(draw, "x" * 80, f, 160), font=f) <= 160
    assert marquee(draw, "short", f, 160, 0.0) == "short"
    assert marquee(draw, "y" * 50, f, 160, 0.0) != marquee(draw, "y" * 50 + "z", f, 160, 100.0)
    lines = wrap(draw, "one two three four five six seven eight nine ten", f, 80)
    assert len(lines) > 1 and all(draw.textlength(l, font=f) <= 80 for l in lines)
