from g13d.lcd.mpris import MprisWatcher

A, B = "org.mpris.MediaPlayer2.a", "org.mpris.MediaPlayer2.b"


def _watcher(status_a: str, status_b: str) -> MprisWatcher:
    w = MprisWatcher()
    w.set_players({A: "A", B: "B"})
    w.update(A, {"PlaybackStatus": status_a})
    w.update(B, {"PlaybackStatus": status_b})
    return w


def test_picks_the_playing_player():
    assert _watcher("Paused", "Playing").active.bus_name == B
    assert _watcher("Paused", "Paused").active.bus_name == A


def test_choice_sticks_on_a_paused_player():
    w = _watcher("Paused", "Playing")
    w.select_next()
    assert w.active.bus_name == A and w.index == 0
    w.update(B, {"PlaybackStatus": "Playing"})        # B keeps playing: stay on A
    assert w.active.bus_name == A


def test_follows_a_player_that_starts():
    w = _watcher("Paused", "Paused")
    w.update(B, {"PlaybackStatus": "Playing"})
    assert w.active.bus_name == B


def test_selected_player_gone():
    w = _watcher("Playing", "Paused")
    w.set_players({B: "B"})
    assert w.active.bus_name == B and w.index == 0
