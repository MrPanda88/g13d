from g13d.config.model import BINDABLE, M_KEYS
from g13d.gui import device_geometry as g


def test_every_bindable_control_has_a_place():
    assert set(BINDABLE) - {"LIGHT"} == set(g.ALL)      # the light key is the hardware's own
    assert set(M_KEYS) == set(g.M_KEYS)


def test_rects_are_inside_the_picture():
    for name, (x, y, w, h) in {**g.ALL, **g.M_KEYS, "press-pill": g.STICK_PRESS_PILL}.items():
        assert 0 <= x < x + w <= 1, name
        assert 0 <= y < y + h <= 1, name
    cx, cy = g.STICK_CENTER
    assert 0 < cx < 1 and 0 < cy < 1


def test_g_keys_do_not_overlap():
    rects = [(n, r) for n, r in g.KEYS.items()]
    for i, (n1, (x1, y1, w1, h1)) in enumerate(rects):
        for n2, (x2, y2, w2, h2) in rects[i + 1:]:
            apart = x1 + w1 <= x2 or x2 + w2 <= x1 or y1 + h1 <= y2 or y2 + h2 <= y1
            assert apart, f"{n1} overlaps {n2}"
