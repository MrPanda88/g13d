"""Find the G13 as exposed by the kernel driver (sysfs), and watch for hotplug via udev."""
from __future__ import annotations

import glob
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from .names import PRODUCT_ID, VENDOR_ID

log = logging.getLogger(__name__)

HID_GLOB = f"/sys/bus/hid/devices/*{VENDOR_ID:04X}:{PRODUCT_ID:04X}*"
HID_ID = f"0003:{VENDOR_ID:08X}:{PRODUCT_ID:08X}"


@dataclass
class G13Paths:
    hid_sysfs: Path
    driver: str | None
    keypad_event: str | None
    stick_event: str | None
    hidraw: str | None
    leds: dict[str, Path] = field(default_factory=dict)  # m1, m2, m3, mr, backlight

    @property
    def complete(self) -> bool:
        return bool(self.keypad_event and self.stick_event and self.hidraw and len(self.leds) == 5)


def find_g13() -> G13Paths | None:
    for hid in sorted(glob.glob(HID_GLOB)):
        hid_path = Path(hid)
        driver = os.path.basename(os.readlink(hid_path / "driver")) if (hid_path / "driver").exists() else None
        keypad = stick = None
        for inp in glob.glob(f"{hid}/input/input*"):
            name = _read(Path(inp) / "name")
            events = glob.glob(f"{inp}/event*")
            if not events:
                continue
            dev = "/dev/input/" + os.path.basename(events[0])
            if "Thumbstick" in name:
                stick = dev
            else:
                keypad = dev
        hidraws = glob.glob(f"{hid}/hidraw/hidraw*")
        hidraw = "/dev/" + os.path.basename(hidraws[0]) if hidraws else None
        leds: dict[str, Path] = {}
        for led in glob.glob(f"{hid}/leds/*"):
            base = os.path.basename(led)
            if base.endswith("macro_preset_1"):
                leds["m1"] = Path(led)
            elif base.endswith("macro_preset_2"):
                leds["m2"] = Path(led)
            elif base.endswith("macro_preset_3"):
                leds["m3"] = Path(led)
            elif base.endswith("macro_record"):
                leds["mr"] = Path(led)
            elif base.endswith("kbd_backlight"):
                leds["backlight"] = Path(led)
        return G13Paths(hid_path, driver, keypad, stick, hidraw, leds)
    return None


def _read(p: Path) -> str:
    try:
        return p.read_text().strip()
    except OSError:
        return ""


def diagnose(paths: G13Paths | None) -> str:
    """Human-readable explanation of why the device is unusable (or 'ok')."""
    if paths is None:
        usb = glob.glob("/sys/bus/usb/devices/*/idProduct")
        for p in usb:
            if _read(Path(p)) == f"{PRODUCT_ID:04x}":
                iface = os.path.dirname(p)
                drivers = [os.path.basename(os.readlink(d)) for d in glob.glob(f"{iface}/*:1.0/driver")]
                if drivers and "usbhid" not in drivers:
                    return (f"G13 is on USB but held by {drivers[0]} instead of usbhid: another driver "
                            f"(libusb based) has detached the kernel driver. Stop it and replug the device.")
                return "G13 is on USB but has no HID device: is the hid_lg_g15 module loaded?"
        return "no G13 connected"
    if paths.driver != "lg-g15":
        return f"G13 HID device is bound to {paths.driver!r}, expected 'lg-g15' (kernel >= 6.19 needed)"
    missing = []
    for label, p in (("keypad evdev", paths.keypad_event), ("stick evdev", paths.stick_event), ("hidraw", paths.hidraw)):
        if not p:
            missing.append(label)
        elif not os.access(p, os.R_OK | os.W_OK):
            missing.append(f"{label} ({p}: permission denied, install the udev rule)")
    for n in ("m1", "m2", "m3", "mr", "backlight"):
        if n not in paths.leds:
            missing.append(f"led {n}")
        elif not os.access(paths.leds[n] / "brightness", os.W_OK):
            missing.append(f"led {n} (not writable, install the udev rule)")
    return "ok" if not missing else "missing: " + ", ".join(missing)
