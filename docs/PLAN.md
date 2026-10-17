# Plan — g13d: native Linux driver for the Logitech G13

Status: **approved on 2026-10-17, M1 in progress.**

## 0. Established facts (validated on hardware on 2026-10-17)

| Part | Mechanism | Verified |
|---|---|---|
| G1–G22, M1–M3, MR, 5 LCD keys | evdev `Logitech G13 Gaming Keypad` (hid-lg-g15) | yes |
| Analog stick + 3 buttons | evdev `Logitech G13 Thumbstick`, `ABS_X/ABS_Y` 0–255 | yes |
| M1/M2/M3/MR LEDs | `/sys/class/leds/g13:red:macro_preset_{1,2,3}`, `g13:red:macro_record` | yes |
| RGB backlight | `/sys/class/leds/g13:rgb:kbd_backlight` (`multi_intensity` + `brightness`) | yes |
| 160×43 LCD | `hidraw`: output report `0x03` + 31 zero bytes + 960 pixel bytes, 8 vertical pixels per byte, index `32 + x + (y//8)*160` | yes |

HID descriptor: input 1 (7 B), output 3 (991 B, LCD), feature 4 (4 B), feature 5 (M-key LEDs), feature 6 (257 B), feature 7 (RGB).
The kernel owns the LEDs: **always** go through sysfs, never through feature reports.

## 1. Architecture decisions

### 1.1 Language: Python ≥ 3.12
Every dependency is packaged by the major distributions (evdev, Pillow, dbus-next, PyGObject/GTK4/libadwaita, pyudev, psutil;
tomllib is in the standard library). evdev → uinput latency in Python is below 1 ms, imperceptible. Fast iteration, and the
daemon and GUI share code (LCD rendering, profile model). Rust/C++ ruled out: longer to build for no visible gain here.

### 1.2 A user-session daemon (`systemd --user`)
- Starts with the graphical session (`graphical-session.target`), restarts on its own after a crash.
- Hardware access through the udev rule `70-g13d.rules`:
  - `TAG+="uaccess"` on the two G13 evdev nodes and on its hidraw → ACL for the seated user, the same mechanism
    GNOME uses for gamepads (which is why the stick worked out of the box).
  - `RUN+=chmod` on `brightness` and `multi_intensity` of the `g13:*` LEDs (sysfs attributes carry no ACLs).
  - `TAG+="uaccess"` on `/dev/uinput`.
- Why not a root system service: the LCD shows session data (time, media players over MPRIS), the GUI talks to the
  daemon without polkit, the configuration lives in `~/.config`. Price: nothing happens before login.

### 1.3 Key path: evdev grab → engine → uinput
- Exclusive `EVIOCGRAB` on the keypad: raw `KEY_MACRO*` events never leak to the compositor.
- One virtual uinput device "g13d virtual input": every keyboard key, `REL_X/Y/WHEEL`, mouse buttons.
- uinput works at kernel level: independent from Wayland/X11, no libei, no portal.
- Actions are stored as **evdev keycodes** (`KEY_Q`), not characters. The GUI shows labels for the real layout
  (`Gdk.Display.translate_key`) and learns a key from a plain press (GTK hardware keycode − 8 = evdev keycode).

### 1.4 Model: profile → 3 M modes → actions
```
Profile (TOML file)
├── name, RGB colour, LCD pages, stick settings
├── M1: { G1: action, …, G22: action, LCD1..LCD4, LCD_MENU, STICK_UP/DOWN/LEFT/RIGHT, STICK_PRESS, STICK_BTN_LEFT, STICK_BTN_DOWN }
├── M2: same
└── M3: same
```
- Actions: `key` (one keycode), `combo` (several keycodes pressed together), `macro` (name), `mouse` (button), `mode`,
  `profile`, `lcd_page`, `none`.
- The M mode is **global to the current profile**; M LEDs stay in sync; the current mode is persisted across restarts.
- Stick, 4 modes per profile: `keys` (4 directions → 4 actions, adjustable dead zone), `mouse` (relative pointer, speed +
  dead zone), `scroll`, `passthrough` (no grab: games and Steam see a joystick).
- Profile switching is manual (GUI, D-Bus, a key action, CLI). No automatic per-window switching in v1: Wayland/GNOME
  does not expose the focused window cleanly; to be studied later with a Shell extension.

### 1.5 Macros
- TOML files in `~/.config/g13d/macros/<name>.toml`: steps `press`, `release`, `tap`, `delay`.
- Asynchronous, cancellable playback; repeat modes: once, while held (the current pass always completes), toggle.
- **Recording happens in the GUI** (no privilege needed): the window has focus, you type, GTK provides keycodes and
  delays. Recording from the MR key alone would require reading the physical keyboard's evdev nodes, which GNOME does
  not grant without the `input` group: not done.

### 1.6 LCD
- `g13d/lcd/framebuffer.py`: validated encoding; pages rendered with Pillow and the Liberation Mono fonts.
- Pages: **status** (profile + M mode; LCD keys 1–3 = M1–M3, key 4 = next profile), **clock**, **system** (CPU with
  temperature, RAM, network throughput via psutil), **media** (MPRIS; keys: previous / play-pause / next / next player),
  **text** (filled with `g13ctl lcd-text -s 0 …`), **blank**.
- LCD keys: by default the round "menu" key (bit 24) cycles pages and the other four are page actions; everything can
  be rebound per profile.
- Event-driven refresh plus 1 Hz for the clock. A full rewrite is 992 bytes: trivial for USB.
- The G13 forgets everything on power loss: LEDs, colour and LCD are reapplied on every (re)connection and after resume.

### 1.7 D-Bus (session bus): `org.g13d.Daemon` at `/org/g13d/Daemon`
- Properties: `Connected`, `CurrentProfile`, `CurrentMode`, `Recording`, `Profiles`, `Macros`, `ActiveMacros`,
  `CurrentLcdPage`, `LcdPages`, `AvailableLcdPages`.
- Methods: `SetProfile(name)`, `SetMode(n)`, `ReloadConfig()`, `SetBacklight(r,g,b)`, `LcdText(text, seconds)`,
  `LcdPage(name)`, `RunMacro(name)`, `StopMacros()`, `SetRecording(b)`, `GetStatus()`.
- Signals: `ProfileChanged`, `ModeChanged`, `DeviceChanged(connected)`, `KeyEvent(name, pressed)` (GUI: live key
  highlight), `RecordingChanged`, `LcdPageChanged`.
- The GUI writes the TOML files, then calls `ReloadConfig()`.

### 1.8 GUI: GTK4 + libadwaita, `g13-gui`
- Adw window: profile sidebar; main view = picture of the G13 (22 keys, 4 LCD keys, stick); M1/M2/M3 selector; click a
  key → action editor (learn a key, combo, macro, mode, profile…).
- Tabs: Stick, LCD & Light (pages and their order, backlight colour, preview), Macros (list, step editor, Record button).
- Desktop entry, English UI.

### 1.9 Command line: `g13ctl`
`status`, `profiles`, `profile <name>`, `mode <1-3>`, `backlight r g b`, `lcd-page`, `lcd-text "…"`, `macros`,
`macro-run`, `macro-stop`, `reload`, `watch`, `diagnose`.

### 1.10 No import of other drivers' configurations
Existing drivers use heterogeneous formats; configuration is redone with Logitech Gaming Software style key learning
(click a G key → "learn" → press the wanted key; macros: Record → type → Stop, delays captured).

## 2. Layout
```
g13d/
├── CLAUDE.md, README.md, LICENSE (MIT), pyproject.toml, Makefile
├── g13d/
│   ├── __init__.py, __main__.py           # python -m g13d
│   ├── config/   model.py (dataclasses), loader.py (TOML ↔ model), defaults.py, macro.py, tomlout.py
│   ├── hw/       discover.py (sysfs + pyudev), keypad.py (evdev + grab), leds.py (sysfs), lcd_dev.py (hidraw), names.py
│   ├── engine/   actions.py, macros.py (player), recorder.py, stick.py, uinput_out.py
│   ├── lcd/      framebuffer.py, fonts.py, screen.py, mpris.py, pages/ (status, clock, system, media, text, blank)
│   ├── daemon/   main.py (asyncio), dbus_service.py
│   ├── gui/      app.py, window.py, keys_page.py, action_editor.py, macros_page.py, stick_page.py, lcd_page.py, …
│   ├── cli/      g13ctl.py
│   └── data/     70-g13d.rules, g13d.service, org.g13d.Gui.desktop
├── scripts/      probe.py, evcap.py, led_test.py, lcd_test.py, lcd_bounds.py, render_pages.py (diagnostics)
├── tests/        pytest: framebuffer, config, engine, macros, pages (no hardware)
└── docs/         PLAN.md, HARDWARE.md (protocol)
```

## 3. Milestones

| # | Content | Verifiable result |
|---|---|---|
| M0 | Hardware validation, probe scripts | **done** |
| M1 | Minimal daemon: discovery, grab, uinput, TOML profile, M modes + LEDs, colour, udev, systemd unit, `g13ctl` | code written, hands-on validation pending |
| M2 | LCD: framebuffer, status/clock/system/media (MPRIS)/text/blank pages, per-page LCD keys, `LcdText` | a live, useful LCD |
| M3 | Macros: TOML format, playback (once / while_held / toggle), safe release, `MacroRecorder` (pure logic for the GUI), `RunMacro`/`StopMacros`/`SetRecording` | the example macro plays |
| M4 | GTK4/Adw GUI: profiles, keys (learning), stick, LCD & colour, macros + recording | everything configurable with the mouse, LCD preview |
| M5 | Hotplug/suspend, MPRIS, docs, `make install` | clean, reproducible installation |
| M6 | **Step 2**: replace the previous userspace (libusb) drivers: stop them, remove their udev rules and autostart entries, let the kernel take the device back | the G13 is handled by g13d alone |

Each milestone: pytest off-hardware + real test on the G13 + commit.

## 4. Decisions (2026-10-17)
1. **Names**: `g13d` (daemon), `g13ctl` (CLI), `g13-gui` (GUI), D-Bus `org.g13d`.
2. **Recording**: in the GUI (no privilege, LGS style). Recording from the MR key alone would need the `input` group: not done.
3. **Default stick**: `keys` mode on the arrow keys, 25 % dead zone. Per profile.
4. **Git repository** initialised locally, GitHub publication afterwards.
5. **Licence**: MIT.
6. **No import** of other drivers' configurations (see §1.10).
