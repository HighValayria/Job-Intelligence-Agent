from __future__ import annotations

import re


def clean_text(text: str | None) -> str:
    if not text:
        return ""
    text = text.replace("\u3000", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_for_fingerprint(text: str | None) -> str:
    cleaned = clean_text(text).lower()
    return re.sub(r"\s+", "", cleaned)

