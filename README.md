# g13d — Logitech G13 on Linux, natively

`g13d` is a user-session daemon, a CLI (`g13ctl`) and a GTK4 GUI (`g13-gui`, coming) for the
Logitech G13 gameboard. It builds on the **kernel driver** (`hid_lg_g15`, G13 support since
Linux 6.19) instead of grabbing the USB device with libusb, so it coexists with the rest of the
system and works the same on Wayland and X11.

Features (see `docs/PLAN.md` for the roadmap):

- 22 G-keys, 4 LCD buttons, thumbstick (arrow keys / pointer / scroll / raw gamepad)
- M1 / M2 / M3 modes with synced LEDs, per-profile RGB backlight
- Profiles in plain TOML files
- 160×43 LCD: status, clock, system pages, text messages from scripts over D-Bus
- Macros with GUI recording (milestone M3/M4)
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
| PyGObject + GTK4 + libadwaita (GUI only) | `g13-gui` | `python3-gobject gtk4 libadwaita` | `python3-gi gir1.2-gtk-4.0 gir1.2-adw-1` | `python-gobject gtk4 libadwaita` |

All Python dependencies are declared in `pyproject.toml`; `pip` resolves them if the distro
packages are missing.

## Install (single user)

```sh
git clone https://github.com/raphael-lang/g13d && cd g13d
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
pages = ["status", "clock", "system"]

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

Then `g13ctl reload`. Key names are Linux evdev names (`KEY_A`, `KEY_LEFTSHIFT`, …); they refer
to physical positions, your keyboard layout is applied by the compositor as usual.

## CLI

```
g13ctl status | profiles | profile NAME | mode 1..3 | backlight R G B
g13ctl lcd-page NAME|next|prev | lcd-text "message" [-s 5] | reload | watch | diagnose
```

## D-Bus

Service `org.g13d`, object `/org/g13d/Daemon`, interface `org.g13d.Daemon`: properties
`Connected`, `CurrentProfile`, `CurrentMode`, `Profiles`, `Recording`; methods `SetProfile`,
`SetMode`, `ReloadConfig`, `SetBacklight`, `LcdPage`, `LcdText`, `GetStatus`; signals
`ProfileChanged`, `ModeChanged`, `DeviceChanged`, `KeyEvent`, `RecordingChanged`.

## Hardware notes

See `docs/HARDWARE.md` for the HID protocol as exposed by the kernel driver (LED class names,
LCD report layout, evdev codes).

## License

MIT.
