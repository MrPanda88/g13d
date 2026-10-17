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
    def set_mode(self, m): pass
    def cycle_profile(self, d): pass


async def main():
    out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
    for name, cls in BUILTIN.items():
        page = cls()
        if isinstance(page, TextPage):
            page.text = " ".join(sys.argv[2:]) or "Hello from g13d\nsecond line"
        page.attach()
        await asyncio.sleep(2.5 if name in ("media", "system") else 0)
        img = new_image(); page.render(ImageDraw.Draw(img), img, Ctx()); page.detach()
        big = img.convert("L").resize((WIDTH * 4, HEIGHT * 4), Image.Resampling.NEAREST)
        big.save(out / f"{name}.png"); print("wrote", out / f"{name}.png")

asyncio.run(main())
