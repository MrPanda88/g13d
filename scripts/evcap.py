#!/usr/bin/env python3
"""Capture G13 evdev events for N seconds (default 15). Read-only, no grab."""
import sys, time, selectors, evdev
from evdev import ecodes
dur = float(sys.argv[1]) if len(sys.argv) > 1 else 15
devs = [evdev.InputDevice(p) for p in evdev.list_devices()]
devs = [d for d in devs if d.info.vendor == 0x046D and d.info.product == 0xC21C]
if not devs:
    sys.exit("no readable G13 evdev device")
sel = selectors.DefaultSelector()
for d in devs:
    print("listening:", d.path, d.name)
    sel.register(d, selectors.EVENT_READ)
print(f"press G keys, M keys, LCD buttons, move the stick... ({dur:.0f}s)")
end = time.monotonic() + dur
seen = set()
while time.monotonic() < end:
    for key, _ in sel.select(timeout=0.2):
        for ev in key.fileobj.read():
            if ev.type == ecodes.EV_KEY:
                name = ecodes.KEY.get(ev.code) or ecodes.BTN.get(ev.code) or ev.code
                if isinstance(name, list): name = name[0]
                print(f"KEY {name} {'down' if ev.value else 'up' if ev.value == 0 else 'repeat'}")
                seen.add(name)
            elif ev.type == ecodes.EV_ABS:
                print(f"ABS {ecodes.ABS[ev.code]} = {ev.value}")
print("distinct keys seen:", sorted(map(str, seen)))
