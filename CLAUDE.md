# g13d — native Linux driver for the Logitech G13

## Goal
A complete userspace driver for the Logitech G13 (046d:c21c) built **on top of the kernel driver
`hid-lg-g15`** (G13 support since Linux 6.19) instead of libusb. Scope:
- Remap G1–G22, LCD keys, thumbstick (modes: keys / mouse / scroll / passthrough)
- M1 / M2 / M3 modes switched with the M keys, LEDs in sync
- Macros with recording (Logitech Gaming Software style, in the GUI), delays, repeat modes
- 160×43 mono LCD: status, clock, system, media, text pages
- RGB backlight per profile
- GTK4 / libadwaita GUI (Wayland native) talking to the daemon over the session D-Bus
- `systemd --user` service + udev rule

## Environment
Developed and tested on Fedora (GNOME, Wayland) with kernel ≥ 6.19 (`hid_lg_g15`), Python ≥ 3.12,
GTK4 ≥ 4.12 and libadwaita ≥ 1.7. A G13 plugged into the development machine allows live testing.

## What the kernel already provides (hid-lg-g15, G13)
- `input`: G keys → `KEY_MACRO1..22`, M1–M3 → `KEY_MACRO_PRESET1..3`, MR → `KEY_MACRO_RECORD_START`,
  LCD keys → `KEY_KBD_LCD_MENU1..5`
- separate joystick `input`: `ABS_X`, `ABS_Y` (0–255), 3 buttons
- `/sys/class/leds/`: `g13:red:macro_preset_1..3`, `g13:red:macro_record`, RGB multicolor backlight
- **No LCD**: we write it ourselves through the device's `hidraw` node (output report: byte 0x03 then
  991 bytes, 160×43, 8 vertical pixels per byte)

## Architecture (Python package `g13d`)
- `g13d/hw/`: device discovery (sysfs + pyudev), evdev reader with exclusive grab, LEDs (sysfs), LCD (hidraw)
- `g13d/engine/`: actions → uinput virtual device, thumbstick
- `g13d/lcd/`: framebuffer encoding, pages, screen manager
- `g13d/daemon/`: asyncio main loop, D-Bus service `org.g13d`
- `g13d/gui/`: GTK4/libadwaita app `g13-gui` (planned); `g13d/cli/`: `g13ctl`
- `g13d/data/`: udev rule, systemd unit, desktop entry
- User config: `~/.config/g13d/config.toml`, `profiles/*.toml`

## Progress
- M0 hardware validation: done (2026-10-17)
- M1 daemon + CLI + udev + systemd: code written, `g13d.service` running, hands-on key validation pending
- Next: M2 LCD pages, M3 macros, M4 GUI, M5 polish, M6 replacing the libusb drivers (see `docs/PLAN.md`)

## Useful commands
- Tests: `make test` (pytest, no hardware needed)
- After a code change: nothing to reinstall (editable install); restart with `systemctl --user restart g13d`
- Logs: `journalctl --user -u g13d -f -o cat`
- State: `g13ctl status`, `g13ctl diagnose`, `g13ctl watch`
- Low-level probes: `scripts/probe.py`, `evcap.py`, `led_test.py`, `lcd_test.py`

## Working rules
- Python ≥ 3.12; dependencies: `evdev`, `dbus-next`, `Pillow`, `pyudev`, `psutil`, `PyGObject` (GUI). Full list in
  `pyproject.toml` and `README.md`
- No libusb, never detach the kernel driver: if the G13 is not under `/sys/bus/hid/drivers/lg-g15/`, another
  userspace (libusb) driver holds the interface
- No import of other drivers' configurations; macro recording happens in the GUI, no `input` group needed
- Always release the evdev grab on exit (otherwise the keys stay dead)
- `/usr/bin/g13` is GnuPG's `g13` program, unrelated to this project
- Small commits, messages in English
