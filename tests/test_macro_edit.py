from g13d.config.macro import Step
from g13d.config.macro_edit import History, partner, replace_key

STEPS = [Step.press("KEY_LEFTSHIFT"), Step.delay(20), Step.press("KEY_B"), Step.tap("KEY_LEFTSHIFT"),
         Step.release("KEY_B"), Step.release("KEY_LEFTSHIFT")]


def test_partner_both_ways():
    assert partner(STEPS, 0) == 5 and partner(STEPS, 5) == 0
    assert partner(STEPS, 2) == 4 and partner(STEPS, 4) == 2
    assert partner(STEPS, 1) is None and partner(STEPS, 3) is None


def test_partner_nested_and_unbalanced():
    s = [Step.press("KEY_A"), Step.press("KEY_A"), Step.release("KEY_A"), Step.release("KEY_A")]
    assert partner(s, 0) == 3 and partner(s, 1) == 2 and partner(s, 2) == 1
    assert partner([Step.press("KEY_A")], 0) is None


def test_replace_key_changes_the_pair():
    out = replace_key(STEPS, 4, "KEY_C")
    assert out[2] == Step.press("KEY_C") and out[4] == Step.release("KEY_C")
    assert out[0] == STEPS[0] and STEPS[2] == Step.press("KEY_B")      # original untouched
    assert replace_key(STEPS, 3, "KEY_X")[3] == Step.tap("KEY_X")
    assert replace_key(STEPS, 1, "KEY_X") == STEPS                       # a wait has no key


def test_history_undo_redo_and_coalescing():
    h = History()
    a, b, c = [Step.delay(1)], [Step.delay(2)], [Step.delay(3)]
    h.push(a)
    h.push(b, tag=("delay", 0))
    h.push(b, tag=("delay", 0))           # same spin: one entry
    assert h.undo(c) == b and h.undo(b) == a and h.undo(a) is None
    assert h.redo(a) == b and h.redo(b) == c and not h.can_redo
    h.undo(c)
    h.push(a)                            # a new change drops the redo branch
    assert not h.can_redo


def test_merge_taps_fast_typing():
    from g13d.config.macro_edit import merge_taps
    # "test" typed fast: T and E overlap, then E and S
    s = [Step.press("KEY_T"), Step.delay(50), Step.press("KEY_E"), Step.delay(30), Step.release("KEY_T"), Step.delay(50),
         Step.press("KEY_S"), Step.delay(20), Step.release("KEY_E"), Step.delay(80), Step.release("KEY_S"),
         Step.delay(20), Step.tap("KEY_T")]
    assert merge_taps(s) == [Step.tap("KEY_T"), Step.delay(50), Step.tap("KEY_E"), Step.delay(80), Step.tap("KEY_S"),
                             Step.delay(120), Step.tap("KEY_T")]


def test_merge_taps_keeps_modifiers_mouse_and_long_holds():
    from g13d.config.macro_edit import merge_taps
    shift_t = [Step.press("KEY_LEFTSHIFT"), Step.press("KEY_T"), Step.release("KEY_LEFTSHIFT"), Step.release("KEY_T")]
    assert merge_taps(shift_t) == [Step.press("KEY_LEFTSHIFT"), Step.tap("KEY_T"), Step.release("KEY_LEFTSHIFT")]
    drag = [Step.press("BTN_LEFT"), Step.delay(20), Step.release("BTN_LEFT")]
    assert merge_taps(drag) == drag
    walk = [Step.press("KEY_W"), Step.delay(300), Step.tap("KEY_SPACE"), Step.delay(300), Step.release("KEY_W")]
    assert merge_taps(walk) == walk
    assert merge_taps([Step.press("KEY_A")]) == [Step.press("KEY_A")]
