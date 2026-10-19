"""Find an icon for the application a profile is linked to, and keep a copy under <config>/icons.

Lookup order, first hit wins:
  Steam game (rule steam_app_<id>, or the SteamAppId of the running process):
    1. the icon Steam installed with the game's desktop shortcut (hicolor steam_icon_<id>)
    2. the game's client icon: hash from Steam's local appinfo.vdf cache (else api.steamcmd.net),
       .ico from Steam's local cache (else Steam's CDN)
  Any application:
    3. the Icon= of the desktop entry whose id, StartupWMClass or executable matches the rule

Blocking (files + network with a short timeout): call it from a thread or an executor.
"""
from __future__ import annotations

import configparser
import io
import json
import logging
import os
import re
import shutil
import struct
import urllib.request
from pathlib import Path

log = logging.getLogger(__name__)

TIMEOUT = 6.0
STEAM_CDN = ("https://cdn.cloudflare.steamstatic.com/steamcommunity/public/images/apps/{appid}/{hash}.{ext}",
             "https://cdn.akamai.steamstatic.com/steamcommunity/public/images/apps/{appid}/{hash}.{ext}")
STEAMCMD_API = "https://api.steamcmd.net/v1/info/{appid}"
_STEAM_RULE = re.compile(r"steam_app_(\d+)", re.IGNORECASE)


def steam_appid(rule: str) -> int | None:
    """The app id in a rule written against a Proton game's window class (steam_app_1086940)."""
    m = _STEAM_RULE.fullmatch(rule.strip())
    return int(m.group(1)) if m else None


def process_steam_appid(pid: int) -> int | None:
    """SteamAppId / SteamGameId from a process environment: Steam sets it for native and Proton games."""
    try:
        env = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
    except OSError:
        return None
    for var in (b"SteamAppId=", b"SteamGameId="):
        for item in env:
            if item.startswith(var) and item[len(var):].isdigit():
                appid = int(item[len(var):])
                if appid:
                    return appid
    return None


def is_auto_icon(icon: str, icons_dir: Path) -> bool:
    """True for an icon this module stored (it may be replaced by a new lookup), not one the user chose."""
    return not icon or Path(icon).parent == icons_dir


def find_icon(rule: str, icons_dir: Path, appid: int | None = None, network: bool = True) -> str:
    """Path of a copy under icons_dir (or a themed icon name), "" when nothing was found."""
    rule = rule.strip()
    appid = appid or steam_appid(rule)
    if appid:
        stem = f"steam_{appid}"
        found = _themed_icon_file(f"steam_icon_{appid}")
        if found:
            return _keep(found, icons_dir, stem)
        data = _steam_client_icon(appid, network)
        if data:
            return _save_ico(data, icons_dir, stem)
    if rule and "*" not in rule:
        icon = _desktop_icon(rule)
        if icon:
            if os.path.isabs(icon):
                return _keep(Path(icon), icons_dir, _safe(rule)) if os.path.exists(icon) else ""
            found = _themed_icon_file(icon)
            return _keep(found, icons_dir, _safe(rule)) if found else icon
    return ""


# ---- storage ------------------------------------------------------------------------------------
def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "app"


def _keep(src: Path, icons_dir: Path, stem: str) -> str:
    icons_dir.mkdir(parents=True, exist_ok=True)
    dest = icons_dir / f"{stem}{src.suffix.lower()}"
    if src.suffix.lower() == ".ico":
        return _save_ico(src.read_bytes(), icons_dir, stem)
    shutil.copyfile(src, dest)
    return str(dest)


def _save_ico(data: bytes, icons_dir: Path, stem: str) -> str:
    """Largest image of a .ico (or any Pillow-readable picture) stored as PNG."""
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(data))
        if im.format == "ICO":
            im.size = max(im.info.get("sizes", {im.size}))
            im.load()
        icons_dir.mkdir(parents=True, exist_ok=True)
        dest = icons_dir / f"{stem}.png"
        im.convert("RGBA").save(dest)
    except Exception as exc:  # noqa: BLE001 - truncated download, unknown format, ...
        log.warning("icon %s: unreadable image: %s", stem, exc)
        return ""
    return str(dest)


# ---- icon themes and desktop entries --------------------------------------------------------------
def _data_dirs() -> list[Path]:
    home = os.environ.get("XDG_DATA_HOME") or os.path.join(os.path.expanduser("~"), ".local", "share")
    dirs = [home] + (os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":")
    dirs += [os.path.join(os.path.expanduser("~"), ".local/share/flatpak/exports/share"), "/var/lib/flatpak/exports/share"]
    out: list[Path] = []
    for d in dirs:
        p = Path(d)
        if d and p not in out and p.is_dir():
            out.append(p)
    return out


def _themed_icon_file(name: str) -> Path | None:
    """Biggest file for an icon name in the hicolor theme (scalable first), else in pixmaps."""
    best: tuple[int, Path] | None = None
    for base in _data_dirs():
        theme = base / "icons" / "hicolor"
        if theme.is_dir():
            for size_dir in theme.iterdir():
                for ext in ("svg", "png"):
                    f = size_dir / "apps" / f"{name}.{ext}"
                    if f.is_file():
                        size = 10_000 if size_dir.name == "scalable" else _leading_int(size_dir.name)
                        if best is None or size > best[0]:
                            best = (size, f)
        if best is None:
            for ext in ("svg", "png"):
                f = base / "pixmaps" / f"{name}.{ext}"
                if f.is_file():
                    best = (0, f)
    return best[1] if best else None


def _leading_int(s: str) -> int:
    m = re.match(r"\d+", s)
    return int(m.group()) if m else 0


def _desktop_icon(rule: str) -> str:
    """Icon= of the desktop entry matching the rule by file id, StartupWMClass or executable name."""
    want = rule.casefold()
    stems = {want, want.removesuffix(".desktop")}       # org.telegram.desktop is an app id, not a file name
    fallback = ""
    for base in _data_dirs():
        apps = base / "applications"
        if not apps.is_dir():
            continue
        for f in apps.rglob("*.desktop"):
            entry = _read_desktop(f)
            icon = entry.get("icon", "")
            if not icon or entry.get("nodisplay", "").lower() == "true":
                continue
            if f.stem.casefold() in stems or entry.get("startupwmclass", "").casefold() == want:
                return icon
            if not fallback and _exec_name(entry.get("exec", "")) == want:
                fallback = icon
    return fallback


def _read_desktop(path: Path) -> dict[str, str]:
    cp = configparser.RawConfigParser(interpolation=None, strict=False)
    try:
        cp.read_string(path.read_text(errors="replace"))
    except (OSError, configparser.Error):
        return {}
    return dict(cp["Desktop Entry"]) if cp.has_section("Desktop Entry") else {}


def _exec_name(exec_line: str) -> str:
    words = [w for w in exec_line.split() if "=" not in w and w not in ("env", "flatpak", "run")]
    return os.path.basename(words[0]).casefold() if words else ""


# ---- Steam ------------------------------------------------------------------------------------------
def _steam_roots() -> list[Path]:
    home = Path(os.path.expanduser("~"))
    out: list[Path] = []
    for p in (home / ".local/share/Steam", home / ".steam/steam", home / ".var/app/com.valvesoftware.Steam/.local/share/Steam"):
        if p.is_dir() and p.resolve() not in [o.resolve() for o in out]:
            out.append(p)
    return out


def _steam_client_icon(appid: int, network: bool) -> bytes | None:
    hashes: dict[str, str] = {}
    for root in _steam_roots():
        common = read_appinfo_common(root / "appcache" / "appinfo.vdf", appid)
        if common:
            hashes = {k: str(common.get(k, "")) for k in ("clienticon", "icon")}
            break
    if not hashes.get("clienticon") and network:
        hashes = _steamcmd_hashes(appid) or hashes
    clienticon, icon = hashes.get("clienticon", ""), hashes.get("icon", "")
    if clienticon:
        for root in _steam_roots():
            f = root / "steam" / "games" / f"{clienticon}.ico"
            if f.is_file():
                return f.read_bytes()
        if network and (data := _cdn(appid, clienticon, "ico")):
            return data
    if icon:                      # 32×32 library icon: better than nothing
        for root in _steam_roots():
            f = root / "appcache" / "librarycache" / str(appid) / f"{icon}.jpg"
            if f.is_file():
                return f.read_bytes()
        if network:
            return _cdn(appid, icon, "jpg")
    return None


def _fetch(url: str) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "g13d"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310 - fixed https URLs
            return r.read()
    except Exception as exc:  # noqa: BLE001 - offline, 404, timeout, ...
        log.info("icon lookup: %s: %s", url, exc)
        return None


def _cdn(appid: int, hash_: str, ext: str) -> bytes | None:
    if not re.fullmatch(r"[0-9a-f]{40}", hash_):
        return None
    for url in STEAM_CDN:
        if data := _fetch(url.format(appid=appid, hash=hash_, ext=ext)):
            return data
    return None


def _steamcmd_hashes(appid: int) -> dict[str, str] | None:
    raw = _fetch(STEAMCMD_API.format(appid=appid))
    try:
        common = json.loads(raw)["data"][str(appid)]["common"] if raw else None
    except (ValueError, KeyError, TypeError):
        return None
    return {k: str(common.get(k, "")) for k in ("clienticon", "icon")} if isinstance(common, dict) else None


# ---- Steam appinfo.vdf (binary KeyValues cache of every app the client knows) ------------------------
_MAGIC_28, _MAGIC_29 = 0x07564428, 0x07564429


def read_appinfo_common(path: Path, appid: int) -> dict | None:
    """The `common` section of one app in appinfo.vdf (format 28 or 29), None when absent or unreadable."""
    try:
        with path.open("rb") as f:
            magic, _universe = struct.unpack("<II", f.read(8))
            if magic not in (_MAGIC_28, _MAGIC_29):
                return None
            strings: list[str] | None = None
            if magic == _MAGIC_29:
                (table_offset,) = struct.unpack("<q", f.read(8))
                start = f.tell()
                f.seek(table_offset)
                (count,) = struct.unpack("<I", f.read(4))
                strings = f.read().split(b"\0")[:count]
                strings = [s.decode("utf-8", "replace") for s in strings]
                f.seek(start)
            while True:
                head = f.read(8)
                if len(head) < 8:
                    return None
                app, size = struct.unpack("<II", head)
                if app == 0:
                    return None
                if app != appid:
                    f.seek(size, os.SEEK_CUR)
                    continue
                blob = f.read(size)
                kv, _ = _read_kv(blob, 60, strings)      # 4+4+8+20+4+20 bytes of entry header
                info = kv.get("appinfo", {})
                common = info.get("common") if isinstance(info, dict) else None
                return common if isinstance(common, dict) else None
    except (OSError, struct.error, IndexError, UnicodeDecodeError) as exc:
        log.info("appinfo.vdf: %s", exc)
        return None


def _read_kv(data: bytes, pos: int, strings: list[str] | None) -> tuple[dict, int]:
    out: dict = {}
    while True:
        kind = data[pos]
        pos += 1
        if kind == 0x08:
            return out, pos
        if strings is not None:
            (idx,) = struct.unpack_from("<I", data, pos)
            key, pos = strings[idx], pos + 4
        else:
            end = data.index(b"\0", pos)
            key, pos = data[pos:end].decode("utf-8", "replace"), end + 1
        if kind == 0x00:
            out[key], pos = _read_kv(data, pos, strings)
        elif kind == 0x01:
            end = data.index(b"\0", pos)
            out[key], pos = data[pos:end].decode("utf-8", "replace"), end + 1
        elif kind in (0x02, 0x04, 0x06):
            (out[key],) = struct.unpack_from("<i", data, pos)
            pos += 4
        elif kind == 0x03:
            (out[key],) = struct.unpack_from("<f", data, pos)
            pos += 4
        elif kind == 0x07:
            (out[key],) = struct.unpack_from("<Q", data, pos)
            pos += 8
        elif kind == 0x0A:
            (out[key],) = struct.unpack_from("<q", data, pos)
            pos += 8
        else:
            raise struct.error(f"unknown KeyValues type {kind:#x}")
