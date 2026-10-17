"""GLib-native client for the g13d session D-Bus API (Gio.DBusProxy, no asyncio)."""
from __future__ import annotations

import logging

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio, GLib, GObject  # noqa: E402

from g13d.daemon.dbus_service import BUS_NAME, INTERFACE, OBJECT_PATH  # noqa: E402

log = logging.getLogger(__name__)


class DaemonClient(GObject.Object):
    """Mirrors the daemon state; emits `changed` on any update, `key-event` on G13 input."""

    __gsignals__ = {
        "changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "key-event": (GObject.SignalFlags.RUN_FIRST, None, (str, bool)),
        "error": (GObject.SignalFlags.RUN_FIRST, None, (str,)),
    }

    def __init__(self) -> None:
        super().__init__()
        self._proxy: Gio.DBusProxy | None = None
        self.available = False          # daemon reachable on the bus
        self.device_connected = False
        self.profile = ""
        self.mode = 1
        self.profiles: list[str] = []
        self.macros: list[str] = []
        self.active_macros: list[str] = []
        self.recording = False
        self.lcd_page = ""
        self.lcd_pages: list[str] = []
        self.available_pages: list[str] = []
        Gio.DBusProxy.new_for_bus(Gio.BusType.SESSION, Gio.DBusProxyFlags.NONE, None, BUS_NAME, OBJECT_PATH,
                                  INTERFACE, None, self._on_proxy_ready)

    # ---- setup --------------------------------------------------------------
    def _on_proxy_ready(self, _src, res) -> None:
        try:
            self._proxy = Gio.DBusProxy.new_for_bus_finish(res)
        except GLib.Error as exc:
            log.error("cannot create D-Bus proxy: %s", exc.message)
            self.emit("error", f"D-Bus unavailable: {exc.message}")
            return
        self._proxy.connect("g-properties-changed", lambda *_: self._sync())
        self._proxy.connect("g-signal", self._on_signal)
        self._proxy.connect("notify::g-name-owner", lambda *_: self._sync())
        self._sync()

    def _prop(self, name: str, default):
        if self._proxy is None:
            return default
        v = self._proxy.get_cached_property(name)
        return v.unpack() if v is not None else default

    def _sync(self) -> None:
        self.available = bool(self._proxy and self._proxy.get_name_owner())
        self.device_connected = bool(self._prop("Connected", False)) if self.available else False
        self.profile = self._prop("CurrentProfile", "")
        self.mode = int(self._prop("CurrentMode", 1) or 1)
        self.profiles = list(self._prop("Profiles", []))
        self.macros = list(self._prop("Macros", []))
        self.active_macros = list(self._prop("ActiveMacros", []))
        self.recording = bool(self._prop("Recording", False))
        self.lcd_page = self._prop("CurrentLcdPage", "")
        self.lcd_pages = list(self._prop("LcdPages", []))
        self.available_pages = list(self._prop("AvailableLcdPages", []))
        self.emit("changed")

    def _on_signal(self, _proxy, _sender, name: str, params: GLib.Variant) -> None:
        if name == "KeyEvent":
            key, pressed = params.unpack()
            self.emit("key-event", key, pressed)
        elif name in ("ProfileChanged", "ModeChanged", "DeviceChanged", "RecordingChanged", "LcdPageChanged"):
            self._sync()

    # ---- calls --------------------------------------------------------------
    def _call(self, method: str, params: GLib.Variant | None = None) -> None:
        if self._proxy is None or not self.available:
            self.emit("error", "g13d is not running")
            return

        def done(proxy, res):
            try:
                proxy.call_finish(res)
            except GLib.Error as exc:
                msg = exc.message.split(":", 1)[-1].strip() if "org.g13d.Error" in exc.message else exc.message
                log.warning("%s failed: %s", method, exc.message)
                self.emit("error", msg)

        self._proxy.call(method, params, Gio.DBusCallFlags.NONE, 5000, None, done)

    def set_profile(self, name: str) -> None:
        self._call("SetProfile", GLib.Variant("(s)", (name,)))

    def set_mode(self, mode: int) -> None:
        self._call("SetMode", GLib.Variant("(u)", (mode,)))

    def reload(self) -> None:
        self._call("ReloadConfig")

    def set_backlight(self, r: int, g: int, b: int) -> None:
        self._call("SetBacklight", GLib.Variant("(uuu)", (r, g, b)))

    def show_lcd_page(self, name: str) -> None:
        self._call("LcdPage", GLib.Variant("(s)", (name,)))

    def lcd_text(self, text: str, seconds: float = 3.0) -> None:
        self._call("LcdText", GLib.Variant("(sd)", (text, seconds)))

    def run_macro(self, name: str) -> None:
        self._call("RunMacro", GLib.Variant("(s)", (name,)))

    def stop_macros(self) -> None:
        self._call("StopMacros")

    def set_recording(self, recording: bool) -> None:
        self._call("SetRecording", GLib.Variant("(b)", (recording,)))

    @staticmethod
    def start_daemon() -> None:
        try:
            Gio.Subprocess.new(["systemctl", "--user", "start", "g13d.service"], Gio.SubprocessFlags.NONE)
        except GLib.Error as exc:
            log.error("cannot start g13d: %s", exc.message)
