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
- `g13d/lcd/`: framebuffer encoding, pages, screen manager, MPRIS watcher. Pages may declare `reserved_buttons`
  (LCD keys they take even when bound, e.g. the profiles page) and `options` (global settings stored in config.toml
  `[lcd] options`, e.g. `clock_style`); `Page.shown(ctx)` runs when a page comes on screen
- `g13d/daemon/`: asyncio main loop, D-Bus service `org.g13d`; `focus.py` listens to the g13d GNOME Shell extension
  (`data/gnome-shell/g13d@g13d.org`, interface `org.g13d.Shell` on gnome-shell's connection) and the daemon switches to
  the profile whose `app` rule matches the focused window, back to `manual_profile` otherwise (`set_profile(automatic=)`).
  `Screen.push_modal()` shows a page over the current one (capture page: LCD3 links the focused app to a profile).
  `config/appicons.py` finds the linked application's icon (Steam: hicolor `steam_icon_<id>`, appinfo.vdf / steamcmd.net
  hash + local or CDN `.ico`; else the desktop entry's Icon) into `<config>/icons/`, on link (GUI and LCD capture)
  and from the menu *Find icon*; an icon outside that folder was chosen by the user and is kept by automatic lookups.
  `locked_profile` (daemon state, state.json) is always the active profile and blocks automatic switching; a
  manual switch to another profile releases it
- `g13d/gui/`: GTK4/libadwaita app `g13-gui`; `g13d/cli/`: `g13ctl`
  - two layouts built by `window.py:_build()` and switched live (`[gui] layout` in config.toml, menu ☰ → Layout):
    `gtk` (KeysPage grid + ProfilesSidebar) and `lgs` (DevicePage photo + LibraryPanel + ProfilesBar); the pre-1.1
    names `classic` / `device` are still accepted in config.toml
  - macros: `macros_page.MacroEditor` edits one macro; the gtk layout wraps it in the Macros tab (`MacrosPage`, list +
    editor), the lgs layout has no Macros tab: macros are created (+ on the library's Macros section) and edited
    (right-click) from the library, the editor replacing the G13 photo (`_keys_stack`, back button or Esc).
    Steps are drawn by `macro_steps.py` in three styles (`[gui] macro_style`: icons / flow / timeline); every change
    of the steps goes through `MacroEditor._change` (undo history, redraw, save); pure helpers (press/release
    partner, key replacement, `merge_taps`, `History`) live in `config/macro_edit.py`. Right-click a step:
    Insert before / after (sets the insertion mark used by Add step and Record)
  - `device_geometry.py`: normalised rects of every control on `data/g13.png` (pure data, tested);
    `DeviceView` scales the photo to fit and places the overlays from them, so nothing drifts on resize
  - `data/g13.png` is generated from `image/g13_naked_template.jpeg` (user-supplied, legends already removed) by
    `scripts/make_device_image.py` (checkerboard keyed out); `scripts/check_geometry.py OUT.png` overlays the rects
- `g13d/data/`: udev rule, systemd unit, desktop entry, device picture, GNOME Shell extension (`make install-extension`;
  the Shell only loads new extensions at login; to test one without logging out: `dbus-run-session -- gnome-shell
  --headless --wayland --no-x11 --virtual-monitor 800x600` and call it on that private bus; delete
  `/run/user/UID/gnome-shell-disable-extensions` if a killed test run left it, or every extension is off at next login)
- User config: `~/.config/g13d/config.toml` (settings incl. the global `[lcd]` pages/options and `[gui]`),
  `profiles/*.toml` (backlight, stick, bindings; `[lcd]` in old profiles is read once for migration), `macros/*.toml`,
  `actions.toml` (assignment library, `config/library.py`, seeded from the profiles' bindings and fed by every binding
  made in the GUI)

## Progress
- M0 hardware validation: done (2026-10-17)
- M1 daemon + CLI + udev + systemd: done, validated by hand (2026-10-17)
- M2 LCD pages (status, clock, system, media/MPRIS, text, blank): done (2026-10-17)
- M3 macros (model, player, recorder logic, D-Bus/CLI): done (2026-10-17)
- M4 GTK4/Adw GUI (`g13d/gui/`): done, test feedback integrated (2026-10-17)
- M5 validated by hand (hotplug, suspend/resume) and M6 done (2026-10-17). Published on GitHub (private) 2026-10-18
- v1.0.0 released 2026-10-18 from branch `release-1.0` (last commit before the LGS layout); main is 1.1.0.dev0
- M7 "LGS" layout (photo, assignment library with drag-and-drop, profile tiles, quick unassign), 2026-10-18 → v1.1.0
- M9 per-application profiles (GNOME Shell extension, focus tracker, LCD capture page, Application dialog), 2026-10-18
- M8 LCD: analog clock with dial styles (incl. exotic ones), profiles page (LCD1–3 reserved), colour picker (wheel +
  RGB + presets), LCD pages global instead of per profile, library sort, LGS side panels only on Keys, 2026-10-18

## Useful commands
- Tests: `make test` (pytest, no hardware needed)
- After a code change: nothing to reinstall (editable install); restart with `systemctl --user restart g13d`
- Logs: `journalctl --user -u g13d -f -o cat`
- State: `g13ctl status`, `g13ctl diagnose`, `g13ctl watch`
- Low-level probes: `scripts/probe.py`, `evcap.py`, `led_test.py`, `lcd_test.py`, `lcd_bounds.py`
  (the active LCD area is exactly 160×43; the backlit window is physically larger than the pixel matrix)
- LCD pages without hardware: `scripts/render_pages.py DIR`, then look at the PNGs
- GUI screenshots without watching: `g13-gui --tab keys|stick|lcd|macros [--mode 2] [--edit G1] [--layout gtk|lgs]
  [--size 900x600] --screenshot out.png` (the window shows for 2 s). Layout-aware labels only appear once the window
  has had focus (Wayland keymap)

## Working rules
- **Consistent UI**: a given kind of control behaves the same everywhere. Text fields = applied on Enter, ✓ button
  or focus loss, Enter / ✓ / a click elsewhere end the editing (`widgets.text_row`); reorderable lists = arrows + drag-and-drop; deletions = `Adw.AlertDialog`
  confirmation; page width = `WidePage` (1100 px); key labels = `keymap.key_label`; context menus = right-click
  `Gtk.PopoverMenu` parented to a widget whose children are never cleared (clearing loops on the popover);
  tooltips only name things (Undo, Refresh…): a behaviour that needs explaining gets a `widgets.info_button` ⓘ
  next to it (hover or click), never a tooltip alone
- Keys accept dropped assignments in both layouts (`dnd.make_action_target`) and are drag sources themselves: a key
  dropped on another moves its assignment (source emptied, target replaced; payload carries `from`). Drag icons are
  `dnd.drag_icon` pills (accent colours), never a snapshot of the widget (invisible over the black photo). An
  assignment made anywhere lands in the library (`MainWindow._assign`). A key shows its assignment's **library name**
  (`MainWindow._label_for`), the tooltip the layout-aware value. Profile commands are identical in both layouts (`profiles_ui.profile_menu`), and so
  is the right-click menu on keys (`widgets.attach_key_menu`: Edit… / Unassign)
- Short key names (`hw/names.py:KEY_LABELS`) are shared by `Action.describe()` (library labels, layout-agnostic) and
  `keymap.key_label()` (layout-aware); keep both in sync when adding keys
- **LCD legibility** (1-bit panel, no anti-aliasing): body text uses `font(11, bold=False)` or larger; bold only from
  13 px up; never below 10 px except single glyphs. Rows are ≥ 11 px apart, text drawn at `y - 1` inside its row,
  and nothing overlaps an inverted (selected) row. Glyphs outside ASCII may be missing from the font: draw symbols
  (arrows, triangles, check marks) with primitives. Check every new or changed page with `scripts/render_pages.py`
  before showing it; the status page is the reference look
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
