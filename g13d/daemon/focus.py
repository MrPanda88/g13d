"""Which window has the focus, as told by the g13d GNOME Shell extension over the session bus.

The extension (g13d/data/gnome-shell/g13d@g13d.org) exports org.g13d.Shell at /org/g13d/Shell on
gnome-shell's connection: GetFocus(), ListWindows() and the FocusChanged signal. Other desktops can
provide the same interface; without it, per-application profiles simply stay off.
"""
from __future__ import annotations

import asyncio
import fnmatch
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field

from dbus_next import Message, MessageType

log = logging.getLogger(__name__)

SHELL_DEST = "org.gnome.Shell"
SHELL_PATH = "/org/g13d/Shell"
SHELL_IFACE = "org.g13d.Shell"
DEBOUNCE = 0.25         # seconds: alt-tab passes through windows quickly
RETRY = 20.0            # seconds between attempts when the extension is not there


@dataclass
class FocusInfo:
    wm_class: str = ""
    wm_class_instance: str = ""
    title: str = ""
    pid: int = 0
    app_id: str = ""
    app_name: str = ""
    sandboxed_app_id: str = ""
    gtk_app_id: str = ""
    process: str = field(default="", compare=False)     # from /proc, filled by from_variant

    @classmethod
    def from_dict(cls, d: dict) -> FocusInfo:
        def g(k: str, default=""):
            v = d.get(k, default)
            return getattr(v, "value", v)
        info = cls(wm_class=str(g("wm_class")), wm_class_instance=str(g("wm_class_instance")), title=str(g("title")),
                   pid=int(g("pid", 0) or 0), app_id=str(g("app_id")), app_name=str(g("app_name")),
                   sandboxed_app_id=str(g("sandboxed_app_id")), gtk_app_id=str(g("gtk_app_id")))
        info.process = process_name(info.pid)
        return info

    @property
    def empty(self) -> bool:
        return not (self.wm_class or self.app_id or self.pid)

    def identifiers(self) -> list[str]:
        """Every name a rule may be written against (first = the one a capture stores)."""
        ids = [self.wm_class, self.wm_class_instance, self.app_id.removesuffix(".desktop"), self.sandboxed_app_id,
               self.gtk_app_id, self.process, self.app_name]
        out: list[str] = []
        for i in ids:
            if i and i not in out:
                out.append(i)
        return out

    @property
    def key(self) -> str:
        """What gets stored in a profile when the user captures this window."""
        ids = self.identifiers()
        return ids[0] if ids else ""

    @property
    def label(self) -> str:
        return self.app_name or self.wm_class or self.process or self.title or "?"

    def matches(self, rule: str) -> bool:
        """rule: an identifier (case-insensitive), or a glob such as steam_app_*."""
        rule = rule.strip().casefold()
        if not rule:
            return False
        for ident in self.identifiers():
            ident = ident.casefold()
            if ident == rule or fnmatch.fnmatchcase(ident, rule):
                return True
        return False


def process_name(pid: int) -> str:
    """Executable name of a pid (empty when unknown or not ours)."""
    if pid <= 0:
        return ""
    try:
        exe = os.readlink(f"/proc/{pid}/exe")
        return os.path.basename(exe)
    except OSError:
        pass
    try:
        with open(f"/proc/{pid}/comm") as f:
            return f.read().strip()
    except OSError:
        return ""


class FocusTracker:
    """Keeps `current` up to date and calls on_change(info) (debounced) when the focus moves."""

    def __init__(self, bus, on_change: Callable[[FocusInfo | None], None]):
        self._bus = bus
        self._on_change = on_change
        self.available = False
        self.current: FocusInfo | None = None
        self._debounce: asyncio.TimerHandle | None = None
        self._retry: asyncio.Task | None = None

    async def start(self) -> None:
        self._bus.add_message_handler(self._on_message)
        await self._bus.call(Message(destination="org.freedesktop.DBus", path="/org/freedesktop/DBus",
                                     interface="org.freedesktop.DBus", member="AddMatch", signature="s",
                                     body=[f"type='signal',interface='{SHELL_IFACE}',member='FocusChanged'"]))
        await self._probe()

    def stop(self) -> None:
        if self._retry is not None:
            self._retry.cancel()
        if self._debounce is not None:
            self._debounce.cancel()

    async def _probe(self) -> None:
        reply = await self._call("GetFocus")
        was = self.available
        self.available = reply is not None
        if self.available:
            if not was:
                log.info("focus tracking: GNOME Shell extension found")
            self._set(FocusInfo.from_dict(reply.body[0]), immediate=True)
        else:
            if was:
                log.warning("focus tracking: GNOME Shell extension gone")
            self.current = None
            if self._retry is None or self._retry.done():
                self._retry = asyncio.get_running_loop().create_task(self._retry_later())

    async def _retry_later(self) -> None:
        await asyncio.sleep(RETRY)
        await self._probe()

    async def _call(self, member: str) -> Message | None:
        try:
            reply = await self._bus.call(Message(destination=SHELL_DEST, path=SHELL_PATH, interface=SHELL_IFACE, member=member))
        except Exception as exc:  # noqa: BLE001 - bus gone, name not owned, ...
            log.debug("focus tracking: %s failed: %s", member, exc)
            return None
        if reply is None or reply.message_type != MessageType.METHOD_RETURN:
            return None
        return reply

    async def list_windows(self) -> list[FocusInfo]:
        reply = await self._call("ListWindows")
        if reply is None:
            return []
        return [FocusInfo.from_dict(d) for d in reply.body[0]]

    def _on_message(self, msg: Message):
        if msg.message_type == MessageType.SIGNAL and msg.interface == SHELL_IFACE and msg.member == "FocusChanged":
            self.available = True
            self._set(FocusInfo.from_dict(msg.body[0]) if msg.body else None)
        return None

    def _set(self, info: FocusInfo | None, immediate: bool = False) -> None:
        if info is not None and info.empty:
            info = None
        self.current = info
        if self._debounce is not None:
            self._debounce.cancel()
        if immediate:
            self._on_change(info)
        else:
            self._debounce = asyncio.get_running_loop().call_later(DEBOUNCE, self._on_change, info)
