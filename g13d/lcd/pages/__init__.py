"""Registry of built-in LCD pages."""
from __future__ import annotations

from .base import Page
from .blank import BlankPage
from .clock import ClockPage
from .media import MediaPage
from .status import StatusPage
from .system import SystemPage
from .text import TextPage

BUILTIN: dict[str, type[Page]] = {
    StatusPage.name: StatusPage,
    ClockPage.name: ClockPage,
    SystemPage.name: SystemPage,
    MediaPage.name: MediaPage,
    TextPage.name: TextPage,
    BlankPage.name: BlankPage,
}


def make_pages(names: list[str]) -> list[Page]:
    pages: list[Page] = []
    seen: set[str] = set()
    for n in names:
        if n in BUILTIN and n not in seen:
            pages.append(BUILTIN[n]())
            seen.add(n)
    return pages or [StatusPage()]
