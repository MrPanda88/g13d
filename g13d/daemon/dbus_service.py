"""Session D-Bus API: org.g13d on /org/g13d/Daemon, interface org.g13d.Daemon."""
from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from dbus_next import DBusError, RequestNameReply
from dbus_next.aio import MessageBus
from dbus_next.constants import PropertyAccess
from dbus_next.service import ServiceInterface, dbus_property, method, signal

from g13d import __version__

if TYPE_CHECKING:
    from .main import Daemon

log = logging.getLogger(__name__)

BUS_NAME = "org.g13d"
OBJECT_PATH = "/org/g13d/Daemon"
INTERFACE = "org.g13d.Daemon"


class DaemonInterface(ServiceInterface):
    def __init__(self, daemon: "Daemon"):
        super().__init__(INTERFACE)
        self._d = daemon

    # ---- properties -------------------------------------------------------
    @dbus_property(access=PropertyAccess.READ)
    def Version(self) -> "s":
        return __version__

    @dbus_property(access=PropertyAccess.READ)
    def Connected(self) -> "b":
        return self._d.connected

    @dbus_property(access=PropertyAccess.READ)
    def CurrentProfile(self) -> "s":
        return self._d.profile_name

    @dbus_property(access=PropertyAccess.READ)
    def CurrentMode(self) -> "u":
        return self._d.mode

    @dbus_property(access=PropertyAccess.READ)
    def Profiles(self) -> "as":
        return sorted(self._d.profiles)

    @dbus_property(access=PropertyAccess.READ)
    def Recording(self) -> "b":
        return self._d.recording

    # ---- methods ----------------------------------------------------------
    @method()
    def SetProfile(self, name: "s"):
        if name not in self._d.profiles:
            raise DBusError("org.g13d.Error.NoSuchProfile", f"no profile named {name!r}")
        self._d.set_profile(name)

    @method()
    def SetMode(self, mode: "u"):
        if mode not in (1, 2, 3):
            raise DBusError("org.g13d.Error.InvalidMode", "mode must be 1, 2 or 3")
        self._d.set_mode(mode)

    @method()
    def ReloadConfig(self):
        self._d.reload_config()

    @method()
    def SetBacklight(self, r: "u", g: "u", b: "u"):
        self._d.set_backlight((r, g, b))

    @method()
    def LcdPage(self, name: "s"):
        self._d.lcd_page(name)

    @method()
    def LcdText(self, text: "s", seconds: "d"):
        self._d.screen.message(text, seconds)

    @method()
    def GetStatus(self) -> "s":
        return json.dumps(self._d.status(), indent=1)

    # ---- signals ----------------------------------------------------------
    @signal()
    def ProfileChanged(self, name: str) -> "s":
        return name

    @signal()
    def ModeChanged(self, mode: int) -> "u":
        return mode

    @signal()
    def DeviceChanged(self, connected: bool) -> "b":
        return connected

    @signal()
    def KeyEvent(self, name: str, pressed: bool) -> "sb":
        return [name, pressed]

    @signal()
    def RecordingChanged(self, recording: bool) -> "b":
        return recording


async def start_bus(daemon: "Daemon") -> tuple[MessageBus, DaemonInterface]:
    bus = await MessageBus().connect()
    iface = DaemonInterface(daemon)
    bus.export(OBJECT_PATH, iface)
    reply = await bus.request_name(BUS_NAME)
    if reply != RequestNameReply.PRIMARY_OWNER:
        raise SystemExit(f"another g13d instance already owns {BUS_NAME} on the session bus")
    log.info("D-Bus: %s exported at %s", BUS_NAME, OBJECT_PATH)
    return bus, iface
