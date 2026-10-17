#!/usr/bin/env python3
"""Cycle M1/M2/M3/MR LEDs, then sweep backlight RGB. Restores backlight to previous value."""
import glob, time
def w(p, v): open(p, "w").write(str(v))
def r(p): return open(p).read().strip()
leds = {n: f"/sys/class/leds/g13:red:{n}" for n in ("macro_preset_1", "macro_preset_2", "macro_preset_3", "macro_record")}
bl = "/sys/class/leds/g13:rgb:kbd_backlight"
prev_rgb, prev_b = r(f"{bl}/multi_intensity"), r(f"{bl}/brightness")
print("backlight before:", prev_rgb, prev_b)
for n, p in leds.items():
    for other in leds.values(): w(f"{other}/brightness", 0)
    w(f"{p}/brightness", 1); print("LED on:", n); time.sleep(0.5)
for p in leds.values(): w(f"{p}/brightness", 0)
w(f"{leds['macro_preset_1']}/brightness", 1)
for rgb in ("255 0 0", "0 255 0", "0 0 255", "255 255 255"):
    w(f"{bl}/multi_intensity", rgb); w(f"{bl}/brightness", 255); print("RGB", rgb); time.sleep(0.6)
w(f"{bl}/multi_intensity", prev_rgb); w(f"{bl}/brightness", prev_b)
print("backlight after :", r(f"{bl}/multi_intensity"), r(f"{bl}/brightness"))
