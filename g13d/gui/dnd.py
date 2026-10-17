"""Drag-and-drop reordering for Gtk.ListBox rows."""
from __future__ import annotations

from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GObject, Gtk  # noqa: E402


def make_reorderable(listbox: Gtk.ListBox, row: Gtk.ListBoxRow, index: int, on_move: Callable[[int, int], None]) -> None:
    """Let `row` (at `index`) be dragged onto other rows of the same list. on_move(src, dest)."""
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
        dest = index if y < row.get_height() / 2 else index + 1
        if src_index < dest:
            dest -= 1
        if src_index != dest:
            on_move(src_index, dest)
        return True
    tgt.connect("drop", drop)
    tgt.connect("enter", lambda *_: (row.add_css_class("g13-drop"), Gdk.DragAction.MOVE)[1])
    tgt.connect("leave", lambda *_: row.remove_css_class("g13-drop"))
    row.add_controller(tgt)
