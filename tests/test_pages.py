"""Render every built-in LCD page off-device."""
from PIL import ImageDraw

from g13d.lcd.framebuffer import encode, new_image
from g13d.lcd.pages import BUILTIN, make_pages
from g13d.lcd.pages.base import fit, marquee
from g13d.lcd.pages.text import TextPage, wrap
from g13d.lcd.fonts import font


class Ctx:
    profile_name = "A rather long profile name that will not fit"
    profile_names = ["Zed", "A rather long profile name that will not fit", "Mid", "Bob", "Eve"]
    mode = 3
    recording = False
    connected = True
    calls = []

    def set_mode(self, m): self.calls.append(("mode", m))
    def cycle_profile(self, d): self.calls.append(("cycle", d))
    def set_profile(self, n): self.calls.append(("profile", n))


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


def test_clock_styles_render():
    from g13d.lcd.pages.clock import STYLES, ClockPage
    outputs = set()
    for style, _label in STYLES:
        page = ClockPage()
        page.configure({"clock_style": style})
        assert page.style == style
        outputs.add(_render(page))
    assert len(outputs) == len(STYLES)          # every style looks different
    page = ClockPage(); page.configure({"clock_style": "bogus"})
    assert page.style == "classic"


def test_profiles_page_navigation():
    from g13d.lcd.pages.profiles import ProfilesPage
    ctx = Ctx(); ctx.calls = []
    page = ProfilesPage()
    assert page.reserved_buttons == (1, 2, 3)
    page.shown(ctx)
    names = sorted(ctx.profile_names)
    assert names[page.cursor] == ctx.profile_name
    assert page.button(2, ctx) and names[page.cursor] == names[(names.index(ctx.profile_name) + 1) % 5]
    for _ in range(5):
        page.button(1, ctx)
    assert page.button(3, ctx)
    assert ctx.calls == [("profile", names[page.cursor])]
    assert not page.button(4, ctx)
    _render(page)                                # with the scrollbar (5 profiles, 3 rows)
    empty = Ctx(); empty.profile_names = []
    assert not page.button(3, empty)


def test_make_pages_passes_options():
    page = make_pages(["clock"], {"clock_style": "digital"})[0]
    assert page.style == "digital"


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
