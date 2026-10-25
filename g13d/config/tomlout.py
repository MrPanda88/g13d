"""Minimal TOML writer for the simple shapes g13d uses (tomli-w is not packaged everywhere).

Supports: str, bool, int, float, lists of scalars, dicts (as tables, nested one level, inline
when used as a value inside a table, unless they hold tables or lists of tables: a sub-table then, since an
inline table must fit on one line). Output always round-trips through tomllib.
"""
from __future__ import annotations

import re

_BARE = re.compile(r"^[A-Za-z0-9_-]+$")


def _key(k: str) -> str:
    return k if _BARE.match(k) else _str(k)


def _str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def _scalar(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(float(v)) if v == v and v not in (float("inf"), float("-inf")) else "0.0"
    if isinstance(v, str):
        return _str(v)
    if isinstance(v, (list, tuple)):
        if any(isinstance(x, dict) for x in v):
            return "[\n" + "".join(f"  {_scalar(x)},\n" for x in v) + "]"
        return "[" + ", ".join(_scalar(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{_key(k)} = {_scalar(x)}" for k, x in v.items()) + " }"
    raise TypeError(f"cannot serialise {type(v).__name__}")


def _needs_table(v) -> bool:
    return isinstance(v, dict) and any(isinstance(x, dict) or (isinstance(x, (list, tuple)) and any(isinstance(y, dict) for y in x))
                                       for x in v.values())


def dumps(data: dict) -> str:
    lines: list[str] = []
    tables: list[tuple[str, dict]] = []
    for k, v in data.items():
        if isinstance(v, dict):
            tables.append((k, v))
        else:
            lines.append(f"{_key(k)} = {_scalar(v)}")
    for name, table in tables:
        if lines and lines[-1] != "":
            lines.append("")
        lines.append(f"[{_key(name)}]")
        sub: list[tuple[str, dict]] = []
        for k, v in table.items():
            if _needs_table(v):
                sub.append((k, v))
            else:
                lines.append(f"{_key(k)} = {_scalar(v)}")
        for sname, stable in sub:
            lines.append("")
            lines.append(f"[{_key(name)}.{_key(sname)}]")
            for k, v in stable.items():
                lines.append(f"{_key(k)} = {_scalar(v)}")
    return "\n".join(lines) + "\n"
