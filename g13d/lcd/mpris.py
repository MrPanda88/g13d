"""Minimal MPRIS2 watcher on the session bus: tracks players, exposes the most relevant one."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from dbus_next import Message, MessageType, Variant
from dbus_next.aio import MessageBus

log = logging.getLogger(__name__)

PREFIX = "org.mpris.MediaPlayer2."
PATH = "/org/mpris/MediaPlayer2"
PLAYER_IFACE = "org.mpris.MediaPlayer2.Player"
ROOT_IFACE = "org.mpris.MediaPlayer2"
POLL = 1.0
RESCAN = 5.0


@dataclass
class Player:
    bus_name: str
    identity: str = ""
    status: str = "Stopped"      # Playing | Paused | Stopped
    title: str = ""
    artist: str = ""
    album: str = ""
    length_us: int = 0
    position_us: int = 0
    can_control: bool = True
    updated: float = field(default_factory=time.monotonic)

    @property
    def position_now_us(self) -> int:
        if self.status != "Playing":
            return self.position_us
        return self.position_us + int((time.monotonic() - self.updated) * 1_000_000)


def _unwrap(v):
    if isinstance(v, Variant):
        return _unwrap(v.value)
    if isinstance(v, dict):
        return {k: _unwrap(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_unwrap(x) for x in v]
    return v


class MprisWatcher:
    def __init__(self) -> None:
        self.players: dict[str, Player] = {}
        self._bus: MessageBus | None = None
        self._task: asyncio.Task | None = None
        self._selected: str | None = None

    # ---- lifecycle --------------------------------------------------------
    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.get_running_loop().create_task(self._run())

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
        if self._bus is not None:
            try:
                self._bus.disconnect()
            except Exception:  # noqa: BLE001
                pass
            self._bus = None
        self.players.clear()

    # ---- selection --------------------------------------------------------
    @property
    def active(self) -> Player | None:
        if not self.players:
            return None
        cur = self.players.get(self._selected or "")
        playing = [p for p in self.players.values() if p.status == "Playing"]
        if cur is not None and (cur.status == "Playing" or not playing):
            return cur
        best = playing[0] if playing else next(iter(self.players.values()))
        self._selected = best.bus_name
        return best

    def select_next(self) -> None:
        names = sorted(self.players)
        if not names:
            return
        try:
            i = names.index(self._selected or "")
        except ValueError:
            i = -1
        self._selected = names[(i + 1) % len(names)]

    # ---- controls ---------------------------------------------------------
    def control(self, member: str) -> None:
        p = self.active
        if p is None or self._bus is None:
            return
        asyncio.get_running_loop().create_task(self._call(p.bus_name, PLAYER_IFACE, member))

    async def _call(self, dest: str, iface: str, member: str, signature: str = "", body: list | None = None) -> Message | None:
        if self._bus is None:
            return None
        try:
            return await self._bus.call(Message(destination=dest, path=PATH, interface=iface,
                                                member=member, signature=signature, body=body or []))
        except Exception as exc:  # noqa: BLE001
            log.debug("mpris call %s.%s on %s failed: %s", iface, member, dest, exc)
            return None

    # ---- polling ----------------------------------------------------------
    async def _run(self) -> None:
        try:
            self._bus = await MessageBus().connect()
            last_scan = 0.0
            while True:
                now = time.monotonic()
                if now - last_scan >= RESCAN:
                    await self._scan()
                    last_scan = now
                for name in list(self.players):
                    await self._refresh(name)
                await asyncio.sleep(POLL)
        except asyncio.CancelledError:
            pass
        except Exception:  # noqa: BLE001
            log.exception("mpris watcher stopped")

    async def _scan(self) -> None:
        assert self._bus is not None
        try:
            reply = await self._bus.call(Message(destination="org.freedesktop.DBus", path="/org/freedesktop/DBus",
                                                 interface="org.freedesktop.DBus", member="ListNames"))
        except Exception as exc:  # noqa: BLE001
            log.debug("ListNames failed: %s", exc)
            return
        names = {n for n in reply.body[0] if n.startswith(PREFIX)}
        for gone in set(self.players) - names:
            del self.players[gone]
        for new in names - set(self.players):
            p = Player(new)
            reply = await self._call(new, "org.freedesktop.DBus.Properties", "Get", "ss", [ROOT_IFACE, "Identity"])
            if reply is not None and reply.message_type == MessageType.METHOD_RETURN and reply.body:
                p.identity = str(_unwrap(reply.body[0]))
            if not p.identity:
                p.identity = new[len(PREFIX):].split(".")[0].capitalize()
            self.players[new] = p

    async def _refresh(self, name: str) -> None:
        p = self.players.get(name)
        if p is None:
            return
        reply = await self._call(name, "org.freedesktop.DBus.Properties", "GetAll", "s", [PLAYER_IFACE])
        if reply is None or reply.message_type != MessageType.METHOD_RETURN or not reply.body:
            return
        props = _unwrap(reply.body[0])
        meta = props.get("Metadata") or {}
        p.status = str(props.get("PlaybackStatus", "Stopped"))
        p.title = str(meta.get("xesam:title", "") or "")
        artist = meta.get("xesam:artist", "")
        p.artist = ", ".join(artist) if isinstance(artist, list) else str(artist or "")
        p.album = str(meta.get("xesam:album", "") or "")
        p.length_us = int(meta.get("mpris:length", 0) or 0)
        p.position_us = int(props.get("Position", 0) or 0)
        p.can_control = bool(props.get("CanControl", True))
        p.updated = time.monotonic()
