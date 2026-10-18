"""g13ctl: command-line client for the g13d daemon (session D-Bus)."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from dbus_next import DBusError
from dbus_next.aio import MessageBus

from g13d import __version__
from g13d.daemon.dbus_service import BUS_NAME, INTERFACE, OBJECT_PATH


async def _iface():
    bus = await MessageBus().connect()
    try:
        intro = await bus.introspect(BUS_NAME, OBJECT_PATH)
    except DBusError as exc:
        sys.exit(f"g13d is not running on the session bus ({exc.text}). Start it: systemctl --user start g13d")
    obj = bus.get_proxy_object(BUS_NAME, OBJECT_PATH, intro)
    return bus, obj.get_interface(INTERFACE)


async def cmd_status(args) -> None:
    _, i = await _iface()
    data = json.loads(await i.call_get_status())
    if args.json:
        print(json.dumps(data, indent=1))
        return
    print(f"g13d {data['version']}  device: {'connected' if data['connected'] else 'absent'} ({data['diagnosis']})")
    print(f"profile: {data['profile']}   mode: M{data['mode']}")
    print(f"profiles: {', '.join(data['profiles'])}")
    print(f"lcd: {data['lcd_page']}  (pages: {', '.join(data['lcd_pages'])})")
    active = f"  running: {', '.join(data['active_macros'])}" if data['active_macros'] else ""
    print(f"macros: {', '.join(data['macros']) or '-'}{active}")
    if data.get("locked_profile"):
        print(f"locked: {data['locked_profile']}  (no automatic switching until unlocked)")
    if data.get("focus_tracking"):
        auto = "on" if data.get("auto_profiles") else "off"
        why = f"  (chosen for it; back to {data['manual_profile']} when it loses the focus)" if data.get("auto_switched") else ""
        print(f"focus: {data.get('focused_app') or '-'}  auto-profiles: {auto}{why}")
    else:
        print("focus: not reported by the desktop (g13d GNOME Shell extension not loaded), auto-profiles inactive")
    print(f"config: {data['config_dir']}")


async def cmd_apps(args) -> None:
    _, i = await _iface()
    apps = await i.call_list_apps()
    if not apps:
        print("no window reported (is the g13d GNOME Shell extension enabled?)")
    for a in sorted(apps, key=lambda a: a["label"].casefold()):
        print(f"{a['key']:<40} {a['label']}  [{a['ids']}]")


async def cmd_capture(args) -> None:
    _, i = await _iface()
    await i.call_capture_app(args.profile)
    print(f"switch to the application, then press LCD 3 on the G13 to link it to {args.profile!r} (LCD 4 cancels)")


async def cmd_lock(args) -> None:
    _, i = await _iface()
    await i.call_set_locked_profile(args.profile or "")


async def cmd_profiles(args) -> None:
    _, i = await _iface()
    current = await i.get_current_profile()
    for p in await i.get_profiles():
        print(("* " if p == current else "  ") + p)


async def cmd_profile(args) -> None:
    _, i = await _iface()
    await i.call_set_profile(args.name)


async def cmd_mode(args) -> None:
    _, i = await _iface()
    await i.call_set_mode(args.mode)


async def cmd_backlight(args) -> None:
    _, i = await _iface()
    await i.call_set_backlight(args.r, args.g, args.b)


async def cmd_lcd_page(args) -> None:
    _, i = await _iface()
    await i.call_lcd_page(args.name)


async def cmd_lcd_text(args) -> None:
    _, i = await _iface()
    await i.call_lcd_text(" ".join(args.text), float(args.seconds))


async def cmd_macros(args) -> None:
    _, i = await _iface()
    active = set(await i.get_active_macros())
    for m in await i.get_macros():
        print(("* " if m in active else "  ") + m)


async def cmd_macro_run(args) -> None:
    _, i = await _iface()
    await i.call_run_macro(args.name)


async def cmd_macro_stop(args) -> None:
    _, i = await _iface()
    await i.call_stop_macros()


async def cmd_reload(args) -> None:
    _, i = await _iface()
    await i.call_reload_config()


async def cmd_watch(args) -> None:
    _, i = await _iface()
    i.on_key_event(lambda name, pressed: print(f"{name} {'down' if pressed else 'up'}", flush=True))
    i.on_mode_changed(lambda m: print(f"mode M{m}", flush=True))
    i.on_profile_changed(lambda p: print(f"profile {p}", flush=True))
    i.on_device_changed(lambda c: print(f"device {'connected' if c else 'disconnected'}", flush=True))
    i.on_lcd_page_changed(lambda n: print(f"lcd {n}", flush=True))
    i.on_focus_changed(lambda a: print(f"focus {a or '-'}", flush=True))
    i.on_recording_changed(lambda r: print(f"recording {'on' if r else 'off'}", flush=True))
    print("watching g13d events, Ctrl-C to stop", file=sys.stderr)
    await asyncio.Event().wait()


def cmd_diagnose(args) -> None:
    from g13d.hw.discover import diagnose, find_g13
    paths = find_g13()
    print(diagnose(paths))
    if paths:
        print(f"hid: {paths.hid_sysfs} (driver {paths.driver})")
        print(f"keypad: {paths.keypad_event}\nstick: {paths.stick_event}\nhidraw: {paths.hidraw}")
        for n, p in sorted(paths.leds.items()):
            print(f"led {n}: {p}")
    import os
    ext = os.path.expanduser("~/.local/share/gnome-shell/extensions/g13d@g13d.org")
    system_ext = "/usr/share/gnome-shell/extensions/g13d@g13d.org"
    where = ext if os.path.isdir(ext) else system_ext if os.path.isdir(system_ext) else None
    print(f"gnome-shell extension (per-application profiles): {'installed at ' + where if where else 'not installed (make install-extension)'}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="g13ctl", description="control the g13d daemon")
    ap.add_argument("--version", action="version", version=f"g13ctl {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("status", help="daemon and device status"); p.add_argument("--json", action="store_true"); p.set_defaults(fn=cmd_status)
    sub.add_parser("profiles", help="list profiles").set_defaults(fn=cmd_profiles)
    p = sub.add_parser("lock", help="lock a profile: it becomes active and applications stop switching profiles; no name = unlock")
    p.add_argument("profile", nargs="?"); p.set_defaults(fn=cmd_lock)
    sub.add_parser("apps", help="list the open windows the desktop reports (for per-application profiles)").set_defaults(fn=cmd_apps)
    p = sub.add_parser("capture", help="link a profile to the next application you focus (confirm with LCD 3)"); p.add_argument("profile"); p.set_defaults(fn=cmd_capture)
    p = sub.add_parser("profile", help="switch profile"); p.add_argument("name"); p.set_defaults(fn=cmd_profile)
    p = sub.add_parser("mode", help="switch M mode"); p.add_argument("mode", type=int, choices=(1, 2, 3)); p.set_defaults(fn=cmd_mode)
    p = sub.add_parser("backlight", help="set backlight colour until next profile change")
    for c in "rgb":
        p.add_argument(c, type=int)
    p.set_defaults(fn=cmd_backlight)
    p = sub.add_parser("lcd-page", help="show an LCD page (name, next, prev)"); p.add_argument("name"); p.set_defaults(fn=cmd_lcd_page)
    p = sub.add_parser("lcd-text", help="show a message on the LCD"); p.add_argument("text", nargs="+"); p.add_argument("-s", "--seconds", type=float, default=3.0, help="overlay duration; 0 = persistent text page"); p.set_defaults(fn=cmd_lcd_text)
    sub.add_parser("macros", help="list macros (* = running)").set_defaults(fn=cmd_macros)
    p = sub.add_parser("macro-run", help="play a macro now"); p.add_argument("name"); p.set_defaults(fn=cmd_macro_run)
    sub.add_parser("macro-stop", help="stop all running macros").set_defaults(fn=cmd_macro_stop)
    sub.add_parser("reload", help="reload configuration files").set_defaults(fn=cmd_reload)
    sub.add_parser("watch", help="print key events and state changes").set_defaults(fn=cmd_watch)
    sub.add_parser("diagnose", help="check the kernel side without the daemon").set_defaults(fn=cmd_diagnose)
    args = ap.parse_args(argv)
    try:
        if asyncio.iscoroutinefunction(args.fn):
            asyncio.run(args.fn(args))
        else:
            args.fn(args)
    except KeyboardInterrupt:
        pass
    except DBusError as exc:
        sys.exit(f"error: {exc.text}")


if __name__ == "__main__":
    main()
