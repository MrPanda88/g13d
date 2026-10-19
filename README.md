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
- 160×43 LCD: status, analog clock (several dials), profile picker, system (CPU/RAM/net), media (MPRIS now-playing with transport buttons), free text and blank pages; messages from scripts over D-Bus
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

Then `g13ctl reload`. `~/.config/g13d/config.toml` holds the global settings: `default_profile` (the
profile loaded when the daemon starts; empty = restore the last one used; the star in the GUI sets
it) and the LCD pages, which are the same whatever the profile:

```toml
[lcd]
pages = ["status", "clock", "system", "media"]   # also: profiles, text, blank
options = { clock_style = "classic" }            # classic | minimal | numbers | plain | radar | orbit | bars | binary | digital
```

The round button left of the LCD keys cycles pages; on the status page the
four LCD keys select M1/M2/M3 and the next profile. Bind `LCD1`..`LCD4` in a profile to override
that, except on the profiles page (up, down, activate, lock) and the media page (previous, play/pause,
next, next player), which keep the four keys for themselves and show what they do along the bottom. Key names are Linux evdev names (`KEY_A`, `KEY_LEFTSHIFT`, …); they refer
to physical positions, your keyboard layout is applied by the compositor as usual.

## Per-application profiles

A profile can be linked to an application: when that application has the focus the G13 switches to
the profile, and goes back to the profile you had chosen when it loses it (alt-tab included). Set it
from the profile's right-click menu → *Application…*: type a rule (window class, app id or process
name, `*` allowed, e.g. `steam_app_*`), pick one of the open windows, or press *Capture*, switch to
the application and press **LCD 3** under the screen. `g13ctl apps` lists what the desktop reports,
`g13ctl capture PROFILE` starts a capture, `auto_profiles = false` in `config.toml` turns the whole
thing off.

Linking an application also fetches its **icon** for the profile tile (kept in `~/.config/g13d/icons/`;
an icon you chose yourself is never replaced). Steam games (`steam_app_<id>`, or any game started by
Steam) get their client icon from Steam's local cache, else from Steam's CDN; other applications get
the icon of their desktop entry. Right-click → *Find icon* runs the lookup again.

A **locked** profile (right-click → *Lock*, `g13ctl lock NAME`, or LCD 4 on the profiles page) is
activated and kept whatever the focused application; one profile at most is locked, switching to
another profile by hand releases the lock.

Wayland does not let a program see the focused window, so this needs a tiny **GNOME Shell
extension** shipped with g13d: `make install-extension`, then log out and back in once. `g13ctl
status` says whether focus tracking is active. Other desktops can provide the same D-Bus interface
(`org.g13d.Shell` at `/org/g13d/Shell`, see `g13d/data/gnome-shell/`).

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

`g13-gui` (also "G13 Configuration" in the app grid) is a GTK4/libadwaita app with two layouts,
switched live from the menu (☰ → Layout):

- **GTK**: profiles in a sidebar, a schematic keypad in the Keys tab.
- **LGS** (after Logitech Gaming Software): the photo of the G13 with every key clickable; an *Assignments* panel on the
  left listing every known assignment and macro (drag one onto a key to bind it, right-click to
  rename / edit / remove, + to add one); profile tiles along the bottom. Key legends take the backlight
  colour of the profile and the assignment floats above each key. When the stick is not in *keys*
  mode its four directions show the mode instead and send you to the Stick tab.

In both:

- **Profiles**: + creates one, based on the default profile when there is one (or any profile you
  pick, or empty); drag to reorder (the LCD and `g13ctl` follow); click one to activate it on the
  device; right-click (or the pencil button in the GTK sidebar) for rename / duplicate / icon / default / delete; the star marks the profile
  loaded at startup. The GUI follows profile and mode switches made on the G13.
- **Keys**: pick M1/M2/M3, click a key, choose what it does (or right-click it: Edit… / Unassign;
  the editor has an Unassign button too). Keys are learned by pressing them (Esc included). A key
  shows the name of its assignment (as listed in the library); its tooltip shows what the key prints
  with your real layout. Keys light up when pressed on the device.
- **Stick**: keys / pointer / scroll / passthrough, dead zone, speeds.
- **LCD & Light**: backlight colour with a hue wheel, R G B sliders and presets (applied live), LCD
  pages on/off and order (drag or arrows), page settings (clock dial style), preview rendered with
  the daemon's code and your backlight colour.
- **Macros**: create, record like Logitech Gaming Software (press Record, type, press Record again
  or MR on the G13; recording replaces the steps), add key or mouse steps by hand, edit delays,
  drag to reorder, play on the device.

Every change is saved immediately and the daemon reloads it. Profiles are plain TOML, so the GUI
and a text editor can be mixed freely. The assignment library lives in `~/.config/g13d/actions.toml`
(label → action); it is seeded from the bindings of your profiles and grows with every binding you
make. Macros are listed from `macros/` directly.

## CLI

```
g13ctl status | profiles | profile NAME | mode 1..3 | backlight R G B | macros | macro-run NAME | macro-stop
g13ctl lcd-page NAME|next|prev | lcd-text "message" [-s 5]  (-s 0: persistent text page) | reload | watch | diagnose
g13ctl apps | capture PROFILE | lock [PROFILE]       (per-application profiles)
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
