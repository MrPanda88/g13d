"""Drag-and-drop reordering for Gtk.ListBox rows."""
from __future__ import annotations

import json
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GObject, Gtk  # noqa: E402

from g13d.config.model import Action, ConfigError  # noqa: E402


def make_reorderable(listbox: Gtk.Widget, row: Gtk.Widget, index: int, on_move: Callable[[int, int], None],
                     horizontal: bool = False) -> None:
    """Let `row` (at `index`) be dragged onto its siblings in `listbox` (any container). on_move(src, dest)."""
    tag = f"g13d-row:{id(listbox)}:"

    src = Gtk.DragSource(actions=Gdk.DragAction.MOVE)
    src.connect("prepare", lambda s, x, y: Gdk.ContentProvider.new_for_value(f"{tag}{index}"))

    def begin(source, _drag):
        source.set_icon(Gtk.WidgetPaintable.new(row), 0, 0)
        row.add_css_class("g13-dragging")
    src.connect("drag-begin", begin)
    src.connect("drag-end", lambda *_: row.remove_css_class("g13-dragging"))
    row.add_controller(src)

    tgt = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.MOVE)

    def drop(_t, value, _x, y):
        row.remove_css_class("g13-drop")
        if not isinstance(value, str) or not value.startswith(tag):
            return False
        src_index = int(value[len(tag):])
        before = (_x < row.get_width() / 2) if horizontal else (y < row.get_height() / 2)
        dest = index if before else index + 1
        if src_index < dest:
            dest -= 1
        if src_index != dest:
            on_move(src_index, dest)
        return True
    tgt.connect("drop", drop)
    tgt.connect("enter", lambda *_: (row.add_css_class("g13-drop"), Gdk.DragAction.MOVE)[1])
    tgt.connect("leave", lambda *_: row.remove_css_class("g13-drop"))
    row.add_controller(tgt)


# ---- dragging actions from the library onto keys -----------------------------------------------
ACTION_TAG = "g13d-action:"


def action_to_payload(action: Action) -> str:
    return ACTION_TAG + json.dumps(action.to_toml())


def payload_to_action(value) -> Action | None:
    """The Action carried by a drop, or None when the drop is not ours."""
    if not isinstance(value, str) or not value.startswith(ACTION_TAG):
        return None
    try:
        return Action.from_toml(json.loads(value[len(ACTION_TAG):]))
    except (ValueError, ConfigError):
        return None


def make_action_source(widget: Gtk.Widget, get_action: Callable[[], Action | None]) -> None:
    """Let `widget` be dragged as the action get_action() returns (None = nothing to drag)."""
    src = Gtk.DragSource(actions=Gdk.DragAction.COPY)

    def prepare(_s, _x, _y):
        action = get_action()
        return None if action is None else Gdk.ContentProvider.new_for_value(action_to_payload(action))
    src.connect("prepare", prepare)
    src.connect("drag-begin", lambda s, _d: s.set_icon(Gtk.WidgetPaintable.new(widget), 0, 0))
    widget.add_controller(src)


def make_action_target(widget: Gtk.Widget, on_drop: Callable[[Action], bool],
                       accepts: Callable[[], bool] = lambda: True) -> None:
    """Accept dragged actions on `widget`; on_drop(action) returns whether it was taken."""
    tgt = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.COPY)

    def enter(_t, _x, _y):
        if not accepts():
            return 0
        widget.add_css_class("g13-drop")
        return Gdk.DragAction.COPY

    def drop(_t, value, _x, _y):
        widget.remove_css_class("g13-drop")
        action = payload_to_action(value)
        return action is not None and accepts() and on_drop(action)
    tgt.connect("enter", enter)
    tgt.connect("leave", lambda *_: widget.remove_css_class("g13-drop"))
    tgt.connect("drop", drop)
    widget.add_controller(tgt)
