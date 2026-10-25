"""g13-gui entry point (GTK4 + libadwaita)."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from g13d import __version__
from g13d.config.loader import ConfigStore

log = logging.getLogger("g13-gui")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="g13-gui", description="Logitech G13 configuration")
    ap.add_argument("--config-dir")
    ap.add_argument("--screenshot", metavar="PNG", help="render the window to a PNG after 2 s and quit (debug)")
    ap.add_argument("--tab", choices=("keys", "stick", "lcd", "macros"), help="tab to show at startup")
    ap.add_argument("--edit", metavar="CONTROL", help="open the action editor for a control at startup (debug)")
    ap.add_argument("--mode", type=int, choices=(1, 2, 3), help="M mode to show in the Keys tab at startup (debug)")
    ap.add_argument("--layout", choices=("lgs", "gtk"), help="window layout for this run (the menu sets the default)")
    ap.add_argument("--size", metavar="WxH", help="initial window size, e.g. 900x600 (debug)")
    ap.add_argument("--link-app", metavar="PROFILE", help="open the application dialog of a profile at startup (debug)")
    ap.add_argument("--profiles-grid", action="store_true", help="open the grid of profiles at startup (lgs layout, debug)")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--version", action="version", version=f"g13-gui {__version__}")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    try:
        import gi
        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
        from gi.repository import Adw, Gio, GLib, Gtk
    except (ImportError, ValueError) as exc:
        sys.exit(f"g13-gui needs PyGObject with GTK 4 and libadwaita 1 (python3-gobject, gtk4, libadwaita): {exc}")

    from .client import DaemonClient
    from .window import MainWindow, about_dialog

    store = ConfigStore(root=Path(args.config_dir).resolve() if args.config_dir else None)
    store.ensure_defaults()

    # single instance for users; debug screenshots must not just wake an already open window
    flags = Gio.ApplicationFlags.NON_UNIQUE if args.screenshot else Gio.ApplicationFlags.DEFAULT_FLAGS
    app = Adw.Application(application_id="org.g13d.Gui", flags=flags)
    state: dict = {}

    def on_activate(application):
        if "win" in state:
            state["win"].present()
            return
        client = DaemonClient()
        win = MainWindow(application, client, store, layout=args.layout)
        state["win"] = win
        layout_action.set_state(GLib.Variant("s", win.layout))
        if args.size:
            w, h = (int(v) for v in args.size.lower().split("x"))
            win.set_default_size(w, h)
        if args.tab:
            win.show_tab(args.tab)
        if args.mode:
            win.show_mode(args.mode)
        win.present()
        if args.edit:
            GLib.timeout_add(300, lambda: (win.edit_control(args.edit), False)[1])
        if args.link_app:
            GLib.timeout_add(600, lambda: (win.link_app_dialog(args.link_app), False)[1])
        if args.profiles_grid:
            GLib.timeout_add(300, lambda: (win.open_profiles_grid(), False)[1])
        if args.screenshot:
            GLib.timeout_add(2000, _screenshot, win, args.screenshot, application)

    def add_action(name, cb):
        a = Gio.SimpleAction.new(name, None)
        a.connect("activate", lambda *_: cb())
        app.add_action(a)

    layout_action = Gio.SimpleAction.new_stateful("layout", GLib.VariantType("s"), GLib.Variant("s", "lgs"))

    def on_layout(action, value):
        action.set_state(value)
        if "win" in state:
            state["win"].set_layout(value.get_string())
    layout_action.connect("change-state", on_layout)
    app.add_action(layout_action)
    add_action("reload", lambda: state["win"].reload_all())
    add_action("about", lambda: about_dialog(state["win"]))
    add_action("open-config", lambda: Gio.AppInfo.launch_default_for_uri(GLib.filename_to_uri(str(store.root), None), None))
    app.connect("activate", on_activate)
    app.run([sys.argv[0]])


def _screenshot(win, path: str, app) -> bool:
    from gi.repository import Gsk, Gtk
    try:
        widget = win
        paintable = Gtk.WidgetPaintable.new(widget)
        snapshot = Gtk.Snapshot()
        paintable.snapshot(snapshot, widget.get_width(), widget.get_height())
        node = snapshot.to_node()
        renderer = win.get_renderer() if hasattr(win, "get_renderer") else None
        if renderer is None:
            renderer = Gsk.CairoRenderer()
            renderer.realize_for_display(win.get_display())
        texture = renderer.render_texture(node, None)
        texture.save_to_png(path)
        log.info("screenshot saved to %s", path)
    except Exception:  # noqa: BLE001
        log.exception("screenshot failed")
    app.quit()
    return False


if __name__ == "__main__":
    main()
