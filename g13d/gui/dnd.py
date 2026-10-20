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


# ---- dragging actions from the library (or from another key) onto keys ----------------------------
ACTION_TAG = "g13d-action:"


def action_to_payload(action: Action, source: str | None = None) -> str:
    """`source`: the key the action is dragged from (a move), None for a library entry (a copy)."""
    data = {"action": action.to_toml()}
    if source is not None:
        data["from"] = source
    return ACTION_TAG + json.dumps(data)


def payload_to_action(value) -> tuple[Action, str | None] | None:
    """(the Action carried by a drop, the key it comes from or None), or None when the drop is not ours."""
    if not isinstance(value, str) or not value.startswith(ACTION_TAG):
        return None
    try:
        data = json.loads(value[len(ACTION_TAG):])
        source = data.get("from")
        return Action.from_toml(data["action"]), source if isinstance(source, str) else None
    except (ValueError, KeyError, TypeError, AttributeError, ConfigError):
        return None


def drag_icon(drag: Gdk.Drag, label: str, icon: str | None = None) -> None:
    """A pill in the accent colour under the pointer: a snapshot of the dragged widget keeps its colours, which
    vanish over the black device picture (light text on no background)."""
    box = Gtk.Box(spacing=6, css_classes=["g13-drag-icon"])
    if icon:
        box.append(Gtk.Image.new_from_icon_name(icon))
    box.append(Gtk.Label(label=label, use_markup=False))
    Gtk.DragIcon.get_for_drag(drag).set_child(box)


def make_action_source(widget: Gtk.Widget, get_action: Callable[[], Action | None], get_label: Callable[[], str],
                       icon: str | None = None, source: str | None = None) -> None:
    """Let `widget` be dragged as the action get_action() returns (None = nothing to drag). With `source` (a key
    name) the drag is a move: the key it comes from is emptied by the drop."""
    src = Gtk.DragSource(actions=Gdk.DragAction.MOVE if source else Gdk.DragAction.COPY)

    def prepare(_s, _x, _y):
        action = get_action()
        return None if action is None else Gdk.ContentProvider.new_for_value(action_to_payload(action, source))

    def begin(_s, drag):
        drag_icon(drag, get_label(), icon)
        widget.add_css_class("g13-dragging")
    src.connect("prepare", prepare)
    src.connect("drag-begin", begin)
    src.connect("drag-end", lambda *_: widget.remove_css_class("g13-dragging"))
    widget.add_controller(src)


def make_action_target(widget: Gtk.Widget, on_drop: Callable[[Action, str | None], bool],
                       accepts: Callable[[], bool] = lambda: True) -> None:
    """Accept dragged actions on `widget`; on_drop(action, source key or None) returns whether it was taken."""
    tgt = Gtk.DropTarget.new(GObject.TYPE_STRING, Gdk.DragAction.COPY | Gdk.DragAction.MOVE)

    def enter(t, _x, _y):
        if not accepts():
            return 0
        widget.add_css_class("g13-drop")
        drop = t.get_current_drop()
        return Gdk.DragAction.MOVE if drop is not None and drop.get_actions() & Gdk.DragAction.MOVE else Gdk.DragAction.COPY

    def drop(_t, value, _x, _y):
        widget.remove_css_class("g13-drop")
        got = payload_to_action(value)
        return got is not None and accepts() and on_drop(*got)
    tgt.connect("enter", enter)
    tgt.connect("leave", lambda *_: widget.remove_css_class("g13-drop"))
    tgt.connect("drop", drop)
    widget.add_controller(tgt)
