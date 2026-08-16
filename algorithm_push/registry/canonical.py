from __future__ import annotations

import re
import unicodedata


_WHITESPACE_RE = re.compile(r"\s+")
_PUNCTUATION_RE = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)
_LEETCODE_NUMBER_RE = re.compile(r"^\s*(?:leetcode\s*)?(\d+)[\.\s、_-]+", re.IGNORECASE)
_NOWCODER_ID_RE = re.compile(r"^\s*((?:NC|BM)\d+)[\.\s、_-]+", re.IGNORECASE)


def normalize_alias(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().lower()
    normalized = _WHITESPACE_RE.sub(" ", normalized)
    normalized = _PUNCTUATION_RE.sub("", normalized)
    return normalized


def slugify_title(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip().lower()
    normalized = _PUNCTUATION_RE.sub("-", normalized)
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    return normalized or "untitled"


def infer_canonical_key(
    *,
    title: str,
    platform: str,
    canonical_key: str | None = None,
) -> str:
    if canonical_key:
        return canonical_key.strip().lower()

    if platform == "leetcode":
        match = _LEETCODE_NUMBER_RE.match(title)
        if match:
            return f"leetcode:{match.group(1)}"
    if platform == "nowcoder":
        match = _NOWCODER_ID_RE.match(title)
        if match:
            return f"nowcoder:{match.group(1).upper()}"

    return f"{platform}:{slugify_title(title)}"
