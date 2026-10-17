#!/usr/bin/env python3
"""Read-only probe: what does the kernel expose for the G13?"""
import glob, os
VID, PID = "046D", "C21C"
print("== HID devices")
for d in glob.glob(f"/sys/bus/hid/devices/*{VID}:{PID}*"):
    drv = os.path.basename(os.path.realpath(os.path.join(d, "driver"))) if os.path.exists(os.path.join(d, "driver")) else None
    print(d, "driver=", drv)
    for sub in ("hidraw", "input"):
        for p in glob.glob(os.path.join(d, sub, "*")):
            print("  ", sub, os.path.basename(p))
            for ev in glob.glob(os.path.join(p, "event*")):
                print("     /dev/input/" + os.path.basename(ev))
print("== LEDs")
for l in sorted(glob.glob("/sys/class/leds/*g13*")) + sorted(glob.glob("/sys/class/leds/*lg-g15*")) + sorted(glob.glob("/sys/class/leds/g15*")):
    extra = ""
    mi = os.path.join(l, "multi_index")
    if os.path.exists(mi):
        extra = " multi=" + open(mi).read().strip()
    print(l, "brightness=", open(os.path.join(l, "brightness")).read().strip(), "max=", open(os.path.join(l, "max_brightness")).read().strip(), extra)
print("== evdev")
try:
    import evdev
    for p in evdev.list_devices():
        dev = evdev.InputDevice(p)
        if dev.info.vendor == 0x046D and dev.info.product == 0xC21C:
            caps = dev.capabilities(verbose=True)
            print(p, dev.name)
            for t, codes in caps.items():
                print("  ", t[0], [c[0] if isinstance(c[0], str) else c[0][0] for c in codes][:40])
except ImportError:
    print("python-evdev absent")
