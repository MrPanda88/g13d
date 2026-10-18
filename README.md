# Disclaimer

I'm a long time developer but I admit I have no credit for coding this.  
I can't play a game without my G13 and wanted a better experience with it.  
So I tried a shot in the dark with Claude and this is just beyond my expectations.  

--

It's 100% claude-coded, I only provided ideas and did the testing.  
It took a bit of time but this is a good V1 (honestly a couple of hours).  
I pushed claude.md and other confs on purpose.  
Feel free to fork it and use it as a base to adapt it to your needs.  
I may also read issues and consider requests even if I won't be the one doing it obviously.  

I have plans for a few updates, mostly QoL as almost every features logitech gaming software was providing is already there.

# g13d — Logitech G13 on Linux, natively

`g13d` is a user-session daemon, a CLI (`g13ctl`) and a GTK4 GUI (`g13-gui`) for the
Logitech G13 gameboard. It builds on the **kernel driver** (`hid_lg_g15`, G13 support since
Linux 6.19) instead of grabbing the USB device with libusb, so it coexists with the rest of the
system and works the same on Wayland and X11.

Features (see `docs/PLAN.md` for the roadmap):

- 22 G-keys, 4 LCD buttons, thumbstick (arrow keys / pointer / scroll / raw gamepad)
- M1 / M2 / M3 modes with synced LEDs, per-profile RGB backlight
- Profiles in plain TOML files
- 160×43 LCD: status, clock, system (CPU/RAM/net), media (MPRIS now-playing with transport buttons), free text and blank pages; messages from scripts over D-Bus
- Macros: press/release/tap/delay steps, play once / while held / toggle, recorder in the GUI
- `systemd --user` service, udev rule, D-Bus API `org.g13d`

## Requirements

| What | Why | Fedora | Debian / Ubuntu | Arch |
|---|---|---|---|---|
| Linux ≥ 6.19 with `hid_lg_g15` | G13 input, LEDs, backlight | kernel | kernel | kernel |
| Python ≥ 3.12 | runtime | `python3` | `python3` | `python` |
| [evdev](https://pypi.org/project/evdev/) | read keypad, write uinput | `python3-evdev` | `python3-evdev` | `python-evdev` |
| [dbus-next](https://pypi.org/project/dbus-next/) | D-Bus API | `python3-dbus-next` | `python3-dbus-next` | `python-dbus-next` |
| [Pillow](https://pypi.org/project/Pillow/) | LCD rendering | `python3-pillow` | `python3-pil` | `python-pillow` |
| [pyudev](https://pypi.org/project/pyudev/) | hotplug | `python3-pyudev` | `python3-pyudev` | `python-pyudev` |
| [psutil](https://pypi.org/project/psutil/) | system LCD page | `python3-psutil` | `python3-psutil` | `python-psutil` |
| PyGObject + GTK4 ≥ 4.12 + libadwaita ≥ 1.7 (GUI only) | `g13-gui` | `python3-gobject gtk4 libadwaita` | `python3-gi gir1.2-gtk-4.0 gir1.2-adw-1` | `python-gobject gtk4 libadwaita` |

All Python dependencies are declared in `pyproject.toml`; `pip` resolves them if the distro
packages are missing.

## Install (single user)

```sh
git clone https://github.com/MrPanda88/g13d && cd g13d
make install-udev     # asks for sudo: /etc/udev/rules.d/70-g13d.rules
make install          # pip install --user -e . ; systemd user unit
make enable           # start now and at every login
g13ctl status
```

If another G13 driver is running (libusb based), stop it first and replug the device: the kernel
driver can only bind when nothing else holds the USB interface. `g13ctl diagnose` tells you what
the kernel sees.

## Configure

Profiles live in `~/.config/g13d/profiles/*.toml`. A `Default` profile is created on first run:

```toml
name = "Default"
backlight = [51, 153, 255]

[stick]
mode = "keys"          # keys | mouse | scroll | passthrough
deadzone = 0.25

[lcd]
pages = ["status", "clock", "system", "media"]   # also: text, blank

[m1]
G1 = "KEY_1"                                 # single key (evdev name)
G8 = { combo = ["KEY_LEFTCTRL", "KEY_C"] }   # several keys together
G9 = { macro = "hello" }                     # macro from ~/.config/g13d/macros/hello.toml
G10 = { mouse = "BTN_LEFT" }
G11 = { mode = 2 }                           # jump to M2
G12 = { profile = "Gaming" }
LCD_MENU = { lcd_page = "next" }
STICK_UP = "KEY_UP"
```

Then `g13ctl reload`. `~/.config/g13d/config.toml` holds `default_profile`: the profile loaded when
the daemon starts (empty = restore the last one used; the star in the GUI sets it).

The round button left of the LCD keys cycles pages; on the status page the
four LCD keys select M1/M2/M3 and the next profile, on the media page they drive the player. Bind
`LCD1`..`LCD4` in a profile to override that. Key names are Linux evdev names (`KEY_A`, `KEY_LEFTSHIFT`, …); they refer
to physical positions, your keyboard layout is applied by the compositor as usual.

## Macros

One TOML file per macro in `~/.config/g13d/macros/`, bound with `{ macro = "name" }`:

```toml
name = "example"
description = "Select the current line and copy it"
repeat = "once"            # once | while_held | toggle
repeat_delay = 0           # ms between loops
steps = [
  { tap = "KEY_HOME" },
  { press = "KEY_LEFTSHIFT" },
  { tap = "KEY_END" },
  { release = "KEY_LEFTSHIFT" },
  { delay = 30 },          # milliseconds
  { press = "KEY_LEFTCTRL" },
  { tap = "KEY_INSERT" },
  { release = "KEY_LEFTCTRL" },
]
```

**Key names are physical positions.** `KEY_A` is the key left of `S`: it types `a` on QWERTY but
`q` on AZERTY, so `Ctrl+KEY_A` is Ctrl+Q there (and quits many apps). When editing TOML by hand on
a non-QWERTY layout, think in QWERTY positions; the GUI records keys by position so you never have to.

Steps may also use mouse buttons (`BTN_LEFT`, `BTN_RIGHT`, `BTN_MIDDLE`, …). `while_held` always
finishes the pass that is playing before it stops, so a macro that types a word never stops
half-way. Keys still held when a macro ends or is stopped are released automatically.
`g13ctl macro-run NAME` plays one immediately, `g13ctl macro-stop` stops everything.

## GUI

`g13-gui` (also "G13 Configuration" in the app grid) is a GTK4/libadwaita app:

- **Profiles**: create, duplicate, rename, delete; click one to activate it on the device; the star
  marks the profile loaded at startup. The GUI follows profile and mode switches made on the G13.
- **Keys**: a picture of the G13; pick M1/M2/M3, click a key, choose what it does. Keys are learned by
  pressing them (Esc included), so labels follow your real layout. Keys light up when pressed on the device.
- **Stick**: keys / pointer / scroll / passthrough, dead zone, speeds.
- **LCD & Light**: backlight colour (live), LCD pages on/off and order (drag or arrows), preview
  rendered with the daemon's code and your backlight colour.
- **Macros**: create, record like Logitech Gaming Software (press Record, type, press Record again
  or MR on the G13; recording replaces the steps), add key or mouse steps by hand, edit delays,
  drag to reorder, play on the device.

Every change is saved immediately and the daemon reloads it. Profiles are plain TOML, so the GUI
and a text editor can be mixed freely.

## CLI

```
g13ctl status | profiles | profile NAME | mode 1..3 | backlight R G B | macros | macro-run NAME | macro-stop
g13ctl lcd-page NAME|next|prev | lcd-text "message" [-s 5]  (-s 0: persistent text page) | reload | watch | diagnose
```

## D-Bus

Service `org.g13d`, object `/org/g13d/Daemon`, interface `org.g13d.Daemon`: properties
`Connected`, `CurrentProfile`, `CurrentMode`, `Profiles`, `Recording`, `CurrentLcdPage`, `LcdPages`,
`AvailableLcdPages`, `Macros`, `ActiveMacros`; methods `SetProfile`,
`SetMode`, `ReloadConfig`, `SetBacklight`, `LcdPage`, `LcdText`, `RunMacro`, `StopMacros`, `SetRecording`,
`GetStatus`; signals
`ProfileChanged`, `ModeChanged`, `DeviceChanged`, `KeyEvent`, `RecordingChanged`, `LcdPageChanged`.

## Hardware notes

See `docs/HARDWARE.md` for the HID protocol as exposed by the kernel driver (LED class names,
LCD report layout, evdev codes).

## License

MIT.
