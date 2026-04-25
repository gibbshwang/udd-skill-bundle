"""Minimal {{variable}} template renderer. No Jinja dependency."""

from __future__ import annotations

import re
from pathlib import Path

_PATTERN = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def render_string(template: str, vars: dict[str, str]) -> str:
    """Substitute {{name}} placeholders. Raises KeyError if a placeholder has no value."""
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in vars:
            raise KeyError(f"Template variable not provided: {key}")
        return str(vars[key])
    return _PATTERN.sub(replace, template)


def render_file(src: Path, dst: Path, vars: dict[str, str]) -> None:
    """Render src template into dst, creating parent dirs as needed."""
    src = Path(src)
    dst = Path(dst)
    content = render_string(src.read_text(encoding="utf-8"), vars)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(content, encoding="utf-8")
