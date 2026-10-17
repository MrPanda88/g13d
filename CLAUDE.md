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
- `g13d/engine/`: actions → uinput virtual device, thumbstick, macro player and recorder
- `g13d/lcd/`: framebuffer encoding, pages, screen manager, MPRIS watcher
- `g13d/daemon/`: asyncio main loop, D-Bus service `org.g13d`
- `g13d/gui/`: GTK4/libadwaita app `g13-gui`; `g13d/cli/`: `g13ctl`
- `g13d/data/`: udev rule, systemd unit, desktop entry
- User config: `~/.config/g13d/config.toml`, `profiles/*.toml`, `macros/*.toml`

## Progress
- M0 hardware validation: done (2026-10-17)
- M1 daemon + CLI + udev + systemd: done, validated by hand (2026-10-17)
- M2 LCD pages (status, clock, system, media/MPRIS, text, blank): done (2026-10-17)
- M3 macros (model, player, recorder logic, D-Bus/CLI): done (2026-10-17)
- M4 GTK4/Adw GUI (`g13d/gui/`): done, test feedback integrated (2026-10-17)
- M5 validated by hand (hotplug, suspend/resume) and M6 done (2026-10-17). Project in use; improvements on request

## Useful commands
- Tests: `make test` (pytest, no hardware needed)
- After a code change: nothing to reinstall (editable install); restart with `systemctl --user restart g13d`
- Logs: `journalctl --user -u g13d -f -o cat`
- State: `g13ctl status`, `g13ctl diagnose`, `g13ctl watch`
- Low-level probes: `scripts/probe.py`, `evcap.py`, `led_test.py`, `lcd_test.py`, `lcd_bounds.py`
  (the active LCD area is exactly 160×43; the backlit window is physically larger than the pixel matrix)
- LCD pages without hardware: `scripts/render_pages.py DIR`, then look at the PNGs
- GUI screenshots without watching: `g13-gui --tab keys|stick|lcd|macros [--mode 2] [--edit G1] --screenshot out.png`
  (the window shows for 2 s). Layout-aware labels only appear once the window has had focus (Wayland keymap)

## Working rules
- **Consistent UI**: a given kind of control behaves the same everywhere. Text fields = applied on Enter, ✓ button
  or focus loss (`MacrosPage._text_row`); reorderable lists = arrows + drag-and-drop; deletions = `Adw.AlertDialog`
  confirmation; page width = `WidePage` (1100 px); key labels = `keymap.key_label`
- `use_markup=False` on every Adw.*Row that shows a key name (`&` and `<` break Pango markup)
- Python ≥ 3.12; dependencies: `evdev`, `dbus-next`, `Pillow`, `pyudev`, `psutil`, `PyGObject` (GUI). Full list in
  `pyproject.toml` and `README.md`
- No libusb, never detach the kernel driver: if the G13 is not under `/sys/bus/hid/drivers/lg-g15/`, another
  userspace (libusb) driver holds the interface
- No import of other drivers' configurations; macro recording happens in the GUI, no `input` group needed
- Always release the evdev grab on exit (otherwise the keys stay dead)
- **Layout trap**: `KEY_*` names are QWERTY positions (`KEY_A` types `q` on AZERTY). Shipped examples and defaults
  must only use layout-independent keys (Home, End, Insert, F1…, Ctrl, Shift)
- `/usr/bin/g13` is GnuPG's `g13` program, unrelated to this project
- Small commits, messages in English
