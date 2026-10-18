"""Registry of built-in LCD pages."""
from __future__ import annotations

from .base import Page
from .blank import BlankPage
from .clock import ClockPage
from .media import MediaPage
from .profiles import ProfilesPage
from .status import StatusPage
from .system import SystemPage
from .text import TextPage

BUILTIN: dict[str, type[Page]] = {
    StatusPage.name: StatusPage,
    ClockPage.name: ClockPage,
    ProfilesPage.name: ProfilesPage,
    SystemPage.name: SystemPage,
    MediaPage.name: MediaPage,
    TextPage.name: TextPage,
    BlankPage.name: BlankPage,
}


def make_pages(names: list[str], options: dict[str, str] | None = None) -> list[Page]:
    pages: list[Page] = []
    seen: set[str] = set()
    for n in names:
        if n in BUILTIN and n not in seen:
            page = BUILTIN[n]()
            page.configure(options or {})
            pages.append(page)
            seen.add(n)
    return pages or [StatusPage()]


def page_options() -> dict[str, tuple[str, list[tuple[str, str]]]]:
    """Every option any built-in page exposes: name -> (label, choices)."""
    out: dict[str, tuple[str, list[tuple[str, str]]]] = {}
    for cls in BUILTIN.values():
        out.update(cls.options)
    return out
