from __future__ import annotations

import re

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_CTRL = re.compile(r"[\x08\x0d]")
_MORE = re.compile(r"----\s*More\s*----")

SANITIZE_PATTERNS = re.compile(
    r"(password|secret|key|token|auth)"
    r"(?:\s*[=:]\s*\S+|\s+cipher\s+\S+)",
    re.IGNORECASE,
)


def clean_output(text: str) -> str:
    text = _ANSI.sub("", text)
    text = _CTRL.sub("", text)
    text = _MORE.sub("", text)
    return text.strip()


def sanitize_command(cmd: str) -> str:
    return SANITIZE_PATTERNS.sub(r"\1=***", cmd)
