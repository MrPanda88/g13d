import struct

from PIL import Image

from g13d.config import appicons


def _kv29(strings: list[str], tree: dict) -> bytes:
    def enc(d: dict) -> bytes:
        out = b""
        for k, v in d.items():
            idx = struct.pack("<I", strings.index(k))
            if isinstance(v, dict):
                out += b"\x00" + idx + enc(v)
            elif isinstance(v, int):
                out += b"\x02" + idx + struct.pack("<i", v)
            else:
                out += b"\x01" + idx + v.encode() + b"\0"
        return out + b"\x08"
    return enc(tree) + b"\x08"


def _appinfo(path, apps: dict[int, dict]) -> None:
    strings = ["appinfo", "appid", "common", "name", "clienticon", "icon"]
    body = b""
    for appid, common in apps.items():
        blob = b"\0" * 60 + _kv29(strings, {"appinfo": {"appid": appid, "common": common}})
        body += struct.pack("<II", appid, len(blob)) + blob
    body += struct.pack("<I", 0)
    table_offset = 16 + len(body)
    table = struct.pack("<I", len(strings)) + b"".join(s.encode() + b"\0" for s in strings)
    path.write_bytes(struct.pack("<IIq", 0x07564429, 1, table_offset) + body + table)


def test_steam_appid_from_rule():
    assert appicons.steam_appid("steam_app_1086940") == 1086940
    assert appicons.steam_appid("STEAM_APP_42 ") == 42
    assert appicons.steam_appid("steam_app_*") is None
    assert appicons.steam_appid("firefox") is None


def test_read_appinfo_common(tmp_path):
    f = tmp_path / "appinfo.vdf"
    _appinfo(f, {10: {"name": "A"}, 1086940: {"name": "BG3", "clienticon": "ab" * 20, "icon": "cd" * 20}})
    assert appicons.read_appinfo_common(f, 1086940) == {"name": "BG3", "clienticon": "ab" * 20, "icon": "cd" * 20}
    assert appicons.read_appinfo_common(f, 10) == {"name": "A"}
    assert appicons.read_appinfo_common(f, 99) is None
    (tmp_path / "bad.vdf").write_bytes(b"nope")
    assert appicons.read_appinfo_common(tmp_path / "bad.vdf", 10) is None


def test_steam_icon_from_local_cache(tmp_path, monkeypatch):
    home = tmp_path / "home"
    steam = home / ".local/share/Steam"
    (steam / "appcache").mkdir(parents=True)
    (steam / "steam/games").mkdir(parents=True)
    _appinfo(steam / "appcache/appinfo.vdf", {7: {"clienticon": "ab" * 20}})
    Image.new("RGBA", (64, 64), "red").save(steam / "steam/games" / f"{'ab' * 20}.ico", sizes=[(16, 16), (64, 64)])
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / ".local/share"))
    monkeypatch.setenv("XDG_DATA_DIRS", str(tmp_path / "none"))
    icon = appicons.find_icon("steam_app_7", tmp_path / "icons", network=False)
    assert icon == str(tmp_path / "icons" / "steam_7.png")
    assert Image.open(icon).size == (64, 64)
    assert appicons.find_icon("steam_app_8", tmp_path / "icons", network=False) == ""


def test_desktop_entry_icon(tmp_path, monkeypatch):
    share = tmp_path / "share"
    (share / "applications").mkdir(parents=True)
    (share / "icons/hicolor/48x48/apps").mkdir(parents=True)
    (share / "icons/hicolor/256x256/apps").mkdir(parents=True)
    Image.new("RGBA", (48, 48)).save(share / "icons/hicolor/48x48/apps/game.png")
    Image.new("RGBA", (256, 256)).save(share / "icons/hicolor/256x256/apps/game.png")
    (share / "applications/org.example.Game.desktop").write_text(
        "[Desktop Entry]\nName=Game\nExec=/opt/game/game-bin %U\nIcon=game\nStartupWMClass=GameWindow\n")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(share))
    monkeypatch.setenv("XDG_DATA_DIRS", str(tmp_path / "none"))
    icons = tmp_path / "icons"
    for rule in ("org.example.Game", "gamewindow", "game-bin"):
        icon = appicons.find_icon(rule, icons, network=False)
        assert Image.open(icon).size == (256, 256), rule
    assert appicons.find_icon("unknown", icons, network=False) == ""
    assert appicons.find_icon("steam_app_*", icons, network=False) == ""


def test_is_auto_icon(tmp_path):
    assert appicons.is_auto_icon("", tmp_path)
    assert appicons.is_auto_icon(str(tmp_path / "steam_7.png"), tmp_path)
    assert not appicons.is_auto_icon("/home/me/Pictures/x.png", tmp_path)
