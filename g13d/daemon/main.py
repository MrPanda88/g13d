"""g13d daemon: glue between the kernel G13 devices, the profile engine and D-Bus."""
from __future__ import annotations

import argparse
import asyncio
import locale
import logging
import os
import signal
import sys

import pyudev

from g13d import __version__
from g13d.config.defaults import default_profile
from g13d.config.loader import ConfigStore
from g13d.config.model import MODES, Action, Profile
from g13d.engine.actions import ActionRunner
from g13d.engine.macros import MacroPlayer
from g13d.engine.stick import Stick
from g13d.engine.uinput_out import VirtualInput
from g13d.hw.discover import G13Paths, diagnose, find_g13
from g13d.hw.keypad import DeviceLost, Keypad
from g13d.hw.lcd_dev import LcdDevice
from g13d.hw.leds import Leds
from g13d.lcd.screen import Screen

from .dbus_service import DaemonInterface, start_bus

log = logging.getLogger("g13d")


class Daemon:
    def __init__(self, store: ConfigStore):
        self.store = store
        self.settings = store.load_settings()
        self.profiles: dict[str, Profile] = store.load_profiles() or {"Default": default_profile()}
        self.macros = store.load_macros()
        state = store.load_state()
        self.profile: Profile = self._pick_profile(state.get("profile"))
        self.mode: int = state.get("mode", 1) if state.get("mode") in MODES else 1
        self.recording = False
        self.connected = False

        self.vinput = VirtualInput()
        self.runner = ActionRunner(self.vinput, self)
        self.player = MacroPlayer(self.vinput, lambda n: self.macros.get(n), self._on_macros_changed)
        self.stick = Stick(self.runner, self.vinput, lambda name: self.profile.binding(self.mode, name))
        self.screen = Screen(self, on_page_change=self._on_lcd_page_change)
        self.keypad: Keypad | None = None
        self.leds: Leds | None = None
        self.lcd: LcdDevice | None = None
        self.paths: G13Paths | None = None
        self.active: dict[str, Action] = {}        # control -> action pressed with it
        self.dbus: DaemonInterface | None = None
        self._wake = asyncio.Event()
        self._last_diag = ""

    # ---- PageContext protocol ---------------------------------------------
    @property
    def profile_name(self) -> str:
        return self.profile.name

    # ---- lifecycle --------------------------------------------------------
    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        stop = asyncio.Event()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        loop.add_signal_handler(signal.SIGHUP, self.reload_config)
        bus, self.dbus = await start_bus(self)
        self._start_udev_monitor(loop)
        self.stick.configure(self.profile.stick)
        self.screen.set_pages(self.profile.lcd_pages)
        worker = asyncio.create_task(self._device_loop())
        log.info("g13d %s ready, profile %r mode M%d", __version__, self.profile.name, self.mode)
        await stop.wait()
        log.info("shutting down")
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
        self.screen.clear()
        self._disconnect()
        self.stick.stop()
        self.vinput.close()
        bus.disconnect()

    def _start_udev_monitor(self, loop: asyncio.AbstractEventLoop) -> None:
        ctx = pyudev.Context()
        monitor = pyudev.Monitor.from_netlink(ctx)
        for sub in ("hid", "input", "hidraw", "leds"):
            monitor.filter_by(sub)
        monitor.start()

        def on_event() -> None:
            dev = monitor.poll(0)
            while dev is not None:
                if "046D:C21C" in dev.sys_path:
                    log.debug("udev %s %s", dev.action, dev.sys_path)
                    self._wake.set()
                dev = monitor.poll(0)

        loop.add_reader(monitor.fileno(), on_event)

    async def _device_loop(self) -> None:
        while True:
            paths = find_g13()
            diag = diagnose(paths)
            if paths is not None and paths.complete and diag == "ok":
                self._last_diag = ""
                try:
                    await self._session(paths)
                except DeviceLost as exc:
                    log.info("G13 disconnected (%s)", exc)
                except PermissionError as exc:
                    log.error("cannot open G13: %s (udev rule 70-g13d.rules installed?)", exc)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    log.exception("device session crashed, retrying")
                    await asyncio.sleep(2)
            elif diag != self._last_diag:
                self._last_diag = diag
                log.info("waiting for G13: %s", diag)
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=5.0)
                await asyncio.sleep(0.3)   # let udev finish creating nodes and ACLs
            except TimeoutError:
                pass

    async def _session(self, paths: G13Paths) -> None:
        assert paths.hidraw
        self.paths = paths
        self.leds = Leds(paths.leds)
        self.lcd = LcdDevice(paths.hidraw)
        self.keypad = Keypad(paths, self.on_key, self.on_stick, grab_stick=self.profile.stick.mode != "passthrough")
        try:
            self.keypad.open()
            self.lcd.open()
            self.connected = True
            log.info("G13 connected: %s", paths.hid_sysfs.name)
            self._apply_hardware()
            if self.dbus:
                self.dbus.DeviceChanged(True)
                self.dbus.emit_properties_changed({"Connected": True})
            await self.keypad.run()
        finally:
            self._disconnect()

    def _disconnect(self) -> None:
        was = self.connected
        self.connected = False
        self._release_everything()
        self.screen.detach()
        if self.keypad:
            self.keypad.close()
            self.keypad = None
        if self.lcd:
            self.lcd.close()
            self.lcd = None
        self.leds = None
        if was and self.dbus:
            self.dbus.DeviceChanged(False)
            self.dbus.emit_properties_changed({"Connected": False})

    def _apply_hardware(self) -> None:
        if self.leds:
            self.leds.set_mode(self.mode)
            self.leds.set_record(self.recording)
            self.leds.set_backlight(self.profile.backlight)
        if self.lcd and self.settings.lcd_enabled:
            self.screen.attach(self.lcd)

    def _release_everything(self) -> None:
        for action in self.active.values():
            self.runner.release(action)
        self.active.clear()
        self.stick.reset()
        self.player.stop_all()
        self.runner.release_all()

    # ---- input callbacks --------------------------------------------------
    def on_key(self, name: str, pressed: bool) -> None:
        if self.dbus:
            self.dbus.KeyEvent(name, pressed)
        if name in ("M1", "M2", "M3"):
            if pressed:
                self.set_mode(int(name[1]))
            return
        if name == "MR":
            return  # the GUI listens to KeyEvent("MR") to start/stop a recording
        if name == "LIGHT":
            return  # the hardware toggles its own backlight
        if pressed:
            prev = self.active.pop(name, None)
            if prev is not None:
                self.runner.release(prev)
            action = self.profile.binding(self.mode, name)
            if name in ("LCD1", "LCD2", "LCD3", "LCD4") and action.type == "none":
                self.screen.button(int(name[3]))
                return
            self.active[name] = action
            self.runner.press(action)
        else:
            action = self.active.pop(name, None)
            if action is not None:
                self.runner.release(action)

    def on_stick(self, x: int, y: int) -> None:
        self.stick.update(x, y)

    # ---- ActionContext protocol -------------------------------------------
    def set_mode(self, mode: int) -> None:
        if mode not in MODES or mode == self.mode:
            return
        self.mode = mode
        if self.leds:
            self.leds.set_mode(mode)
        self.screen.refresh(force=True)
        self._save_state()
        log.info("mode M%d", mode)
        if self.dbus:
            self.dbus.ModeChanged(mode)
            self.dbus.emit_properties_changed({"CurrentMode": mode})

    def set_profile(self, name: str) -> None:
        prof = self.profiles.get(name)
        if prof is None:
            log.warning("unknown profile %r", name)
            return
        self._activate(prof)
        self._save_state()
        log.info("profile %r", prof.name)
        if self.dbus:
            self.dbus.ProfileChanged(prof.name)
            self.dbus.emit_properties_changed({"CurrentProfile": prof.name})

    def _activate(self, prof: Profile) -> None:
        self._release_everything()
        self.profile = prof
        self.stick.configure(prof.stick)
        if self.keypad:
            self.keypad.set_passthrough(prof.stick.mode == "passthrough")
        if self.leds:
            self.leds.set_backlight(prof.backlight)
        self.screen.set_pages(prof.lcd_pages)

    def lcd_page(self, name: str) -> None:
        self.screen.show(name)

    def lcd_text(self, text: str, seconds: float) -> None:
        if seconds > 0:
            self.screen.message(text, seconds)
        else:
            self.screen.set_text(text)

    def _on_lcd_page_change(self, name: str) -> None:
        if self.dbus:
            self.dbus.LcdPageChanged(name)
            self.dbus.emit_properties_changed({"CurrentLcdPage": name})

    def cycle_profile(self, delta: int) -> None:
        names = sorted(self.profiles)
        if len(names) < 2:
            return
        i = names.index(self.profile.name) if self.profile.name in names else 0
        self.set_profile(names[(i + delta) % len(names)])

    def run_macro(self, name: str, pressed: bool) -> None:
        self.player.trigger(name, pressed)

    def _on_macros_changed(self) -> None:
        if self.dbus:
            self.dbus.emit_properties_changed({"ActiveMacros": self.player.active})

    def set_recording(self, recording: bool) -> None:
        if recording == self.recording:
            return
        self.recording = recording
        if self.leds:
            self.leds.set_record(recording)
        self.screen.refresh(force=True)
        if self.dbus:
            self.dbus.RecordingChanged(recording)
            self.dbus.emit_properties_changed({"Recording": recording})

    def set_backlight(self, rgb: tuple[int, int, int]) -> None:
        if self.leds:
            self.leds.set_backlight(rgb)

    # ---- config -----------------------------------------------------------
    def reload_config(self) -> None:
        self.settings = self.store.load_settings()
        profiles = self.store.load_profiles()
        if not profiles:
            log.error("no valid profile found in %s, keeping the current ones", self.store.profiles_dir)
            return
        self.profiles = profiles
        self.macros = self.store.load_macros()
        current = profiles.get(self.profile.name) or self._pick_profile(None)
        self._activate(current)
        self._save_state()
        log.info("configuration reloaded (%d profiles, %d macros), active %r", len(profiles), len(self.macros), current.name)
        if self.dbus:
            self.dbus.emit_properties_changed({"Profiles": sorted(profiles), "CurrentProfile": current.name,
                                               "Macros": sorted(self.macros)})

    def _pick_profile(self, wanted: str | None) -> Profile:
        """Startup profile: the configured default if any, else the last used one, else the first."""
        for name in (self.settings.default_profile, wanted):
            if name and name in self.profiles:
                return self.profiles[name]
        return next(iter(self.profiles.values()))

    def _save_state(self) -> None:
        try:
            self.store.save_state({"profile": self.profile.name, "mode": self.mode})
        except OSError as exc:
            log.warning("cannot save state: %s", exc)

    def status(self) -> dict:
        paths = self.paths if self.connected else find_g13()
        return {
            "version": __version__,
            "connected": self.connected,
            "diagnosis": diagnose(paths),
            "profile": self.profile.name,
            "mode": self.mode,
            "profiles": sorted(self.profiles),
            "default_profile": self.settings.default_profile,
            "macros": sorted(self.macros),
            "active_macros": self.player.active,
            "recording": self.recording,
            "lcd_page": self.screen.current.name,
            "lcd_pages": self.screen.page_names,
            "config_dir": str(self.store.root),
            "keypad": paths.keypad_event if paths else None,
            "stick": paths.stick_event if paths else None,
            "hidraw": paths.hidraw if paths else None,
        }


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="g13d", description="Logitech G13 user daemon")
    ap.add_argument("--config-dir", help="configuration directory (default: ~/.config/g13d)")
    ap.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    ap.add_argument("--version", action="version", version=f"g13d {__version__}")
    args = ap.parse_args(argv)

    try:
        locale.setlocale(locale.LC_ALL, "")   # dates on the LCD in the user's language
    except locale.Error:
        pass
    store = ConfigStore(root=args.config_dir and os.path.abspath(args.config_dir) or None)
    store.ensure_defaults()
    settings = store.load_settings()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else getattr(logging, settings.log_level, logging.INFO),
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    try:
        asyncio.run(Daemon(store).run())
    except PermissionError as exc:
        log.error("%s — is /dev/uinput accessible? (udev rule 70-g13d.rules)", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
