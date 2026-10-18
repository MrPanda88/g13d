#!/usr/bin/env python3
"""Render every LCD page to PNG (scaled x4) for a visual check without the device.
usage: render_pages.py OUT_DIR [text for the text page]"""
import asyncio, sys, time
from pathlib import Path
from PIL import Image, ImageDraw
from g13d.lcd.framebuffer import new_image, WIDTH, HEIGHT
from g13d.lcd.pages import BUILTIN
from g13d.lcd.pages.text import TextPage


class Ctx:
    profile_name = "Default"; mode = 2; recording = False; connected = True
    profile_names = ["Default", "Diablo III", "StarCraft II", "Titanfall"]; focused_app = "Diablo III"; locked_profile = "StarCraft II"
    def set_mode(self, m): pass
    def cycle_profile(self, d): pass
    def set_profile(self, n): pass
    def set_locked_profile(self, n): pass


async def main():
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    from g13d.lcd.pages.clock import STYLES
    variants = [(name, {}) for name in BUILTIN] + [("clock", {"clock_style": s}) for s, _ in STYLES[1:]]
    from g13d.lcd.pages.capture import CapturePage
    cap = CapturePage("Gaming", lambda: None, lambda: None); ctx = Ctx(); cap.shown(ctx)
    img = new_image(); cap.render(ImageDraw.Draw(img), img, ctx)
    img.convert("L").resize((WIDTH * 4, HEIGHT * 4), Image.Resampling.NEAREST).save(out / "capture.png"); print("wrote", out / "capture.png")
    for name, options in variants:
        page = BUILTIN[name](); page.configure(options)
        if isinstance(page, TextPage):
            page.text = " ".join(sys.argv[2:]) or "Hello from g13d\nsecond line"
        page.attach()
        await asyncio.sleep(2.5 if name in ("media", "system") else 0)
        ctx = Ctx(); page.shown(ctx)
        img = new_image(); page.render(ImageDraw.Draw(img), img, ctx); page.detach()
        big = img.convert("L").resize((WIDTH * 4, HEIGHT * 4), Image.Resampling.NEAREST)
        suffix = "-" + "-".join(options.values()) if options else ""
        big.save(out / f"{name}{suffix}.png"); print("wrote", out / f"{name}{suffix}.png")

asyncio.run(main())
