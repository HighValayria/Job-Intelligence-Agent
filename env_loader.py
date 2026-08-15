from __future__ import annotations

import os
import re
from pathlib import Path

_KEY_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def load_env_file(path: Path | str = ".env", *, override: bool = False) -> bool:
    """Load KEY=VALUE pairs from a .env file into os.environ."""
    env_path = Path(path)
    if not env_path.exists():
        return False

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        parsed = _parse_line(raw_line)
        if parsed is None:
            continue
        key, value = parsed
        if override or key not in os.environ:
            os.environ[key] = value
    return True


def _parse_line(raw_line: str) -> tuple[str, str] | None:
    line = raw_line.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("export "):
        line = line[len("export ") :].lstrip()

    key, separator, value = line.partition("=")
    if not separator:
        return None
    key = key.strip()
    if not _KEY_PATTERN.match(key):
        return None

    return key, _parse_value(value.strip())


def _parse_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        unquoted = value[1:-1]
        if value[0] == '"':
            return bytes(unquoted, "utf-8").decode("unicode_escape")
        return unquoted

    comment_index = _find_inline_comment(value)
    if comment_index is not None:
        value = value[:comment_index].rstrip()
    return value


def _find_inline_comment(value: str) -> int | None:
    for index, character in enumerate(value):
        if character == "#" and (index == 0 or value[index - 1].isspace()):
            return index
    return None
