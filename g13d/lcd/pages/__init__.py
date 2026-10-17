"""Registry of built-in LCD pages."""
from __future__ import annotations

from .base import Page
from .clock import ClockPage
from .status import StatusPage

BUILTIN: dict[str, type[Page]] = {
    StatusPage.name: StatusPage,
    ClockPage.name: ClockPage,
}


def make_pages(names: list[str]) -> list[Page]:
    pages = [BUILTIN[n]() for n in names if n in BUILTIN]
    return pages or [StatusPage()]
