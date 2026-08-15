from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime
from hashlib import sha256
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from collectors.base import Collector
from models.raw_post import RawPost

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
SKIP_TAGS = {"script", "style", "noscript", "svg", "template"}
IMAGE_ATTRS = ("src", "data-src", "data-original", "data-lazy-src")
PLATFORM_HOST_HINTS = {
    "xiaohongshu": ("xiaohongshu.com", "xhslink.com"),
    "nowcoder": ("nowcoder.com",),
}


class HtmlSnapshotCollector(Collector):
    """Collect saved HTML snapshots from a local inbox directory."""

    def __init__(
        self,
        inbox_dir: Path | str = "data/inbox/html",
        *,
        default_platform: str = "html_snapshot",
    ) -> None:
        self.inbox_dir = Path(inbox_dir)
        self.default_platform = default_platform

    def collect(self, queries: Sequence[dict[str, Any]] | None = None) -> list[RawPost]:
        del queries
        if not self.inbox_dir.exists():
            return []

        posts: list[RawPost] = []
        seen: set[tuple[str, str]] = set()
        for html_path in _iter_html_files(self.inbox_dir):
            raw_post = parse_html_snapshot(
                html_path,
                root=self.inbox_dir,
                default_platform=self.default_platform,
            )
            key = (raw_post.platform, raw_post.post_id)
            if key in seen:
                continue
            seen.add(key)
            posts.append(raw_post)
        return posts


def parse_html_snapshot(
    html_path: Path | str,
    *,
    root: Path | str | None = None,
    default_platform: str = "html_snapshot",
) -> RawPost:
    path = Path(html_path)
    root_path = Path(root) if root is not None else path.parent
    parser = _SnapshotParser()
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    parser.close()

    metadata = parser.metadata
    url = _first_non_empty(
        metadata.get("job-intel:url"),
        metadata.get("source_url"),
        metadata.get("source-url"),
        metadata.get("url"),
        metadata.get("og:url"),
        parser.canonical_url,
        parser.source_url,
        "",
    )
    title = _first_non_empty(
        parser.title,
        metadata.get("job-intel:title"),
        metadata.get("title"),
        metadata.get("og:title"),
        path.stem,
    )
    platform = _resolve_platform(
        path=path,
        root=root_path,
        url=url,
        metadata=metadata,
        default_platform=default_platform,
    )
    images, remote_images = _resolve_images(path, parser.image_sources)
    post_id = _resolve_post_id(path=path, root=root_path, url=url, metadata=metadata)

    return RawPost(
        post_id=post_id,
        platform=platform,
        url=url,
        title=title,
        author=_first_non_empty(
            metadata.get("author"),
            metadata.get("article:author"),
            metadata.get("job-intel:author"),
            None,
        ),
        publish_time=_parse_datetime(
            _first_non_empty(
                metadata.get("article:published_time"),
                metadata.get("published_time"),
                metadata.get("publish_time"),
                metadata.get("date"),
                metadata.get("job-intel:publish-time"),
                None,
            )
        ),
        text=parser.visible_text,
        images=images,
        metadata={
            "source_type": "html_snapshot",
            "source_file": str(path),
            "canonical_url": url,
            "remote_images": remote_images,
        },
    )


class _SnapshotParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.metadata: dict[str, str] = {}
        self.canonical_url = ""
        self.source_url = ""
        self.title = ""
        self.visible_text = ""
        self.image_sources: list[str] = []
        self._skip_depth = 0
        self._in_title = False
        self._title_parts: list[str] = []
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attr_map = {key.lower(): value or "" for key, value in attrs}
        if tag in SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag == "title":
            self._in_title = True
        if tag == "meta":
            key = _first_non_empty(
                attr_map.get("name"),
                attr_map.get("property"),
                attr_map.get("itemprop"),
                "",
            )
            value = attr_map.get("content", "")
            if key and value:
                self.metadata[key.strip().lower()] = unescape(value.strip())
        if tag == "link":
            rel = attr_map.get("rel", "").lower()
            href = attr_map.get("href", "")
            if "canonical" in rel and href:
                self.canonical_url = unescape(href.strip())
        if tag == "img":
            source = _first_non_empty(*(attr_map.get(attr) for attr in IMAGE_ATTRS), "")
            if source:
                self.image_sources.append(unescape(source.strip()))
        if attr_map.get("data-source-url"):
            self.source_url = unescape(attr_map["data-source-url"].strip())
        if attr_map.get("data-platform"):
            self.metadata.setdefault("platform", unescape(attr_map["data-platform"].strip()))

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
            return
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self._title_parts.append(data)
            return
        self._text_parts.append(data)

    def handle_comment(self, data: str) -> None:
        match = re.search(r"(?:source_url|source-url|url)\s*:\s*(\S+)", data, re.I)
        if match and not self.source_url:
            self.source_url = match.group(1).strip()
        match = re.search(r"platform\s*:\s*([A-Za-z0-9_.-]+)", data, re.I)
        if match:
            self.metadata.setdefault("platform", match.group(1).strip())

    def close(self) -> None:
        super().close()
        self.title = _collapse_text(self._title_parts)
        self.visible_text = _collapse_text(self._text_parts)


def _iter_html_files(root: Path) -> list[Path]:
    return sorted(
        [*root.rglob("*.html"), *root.rglob("*.htm")],
        key=lambda path: str(path).lower(),
    )


def _resolve_post_id(
    *,
    path: Path,
    root: Path,
    url: str,
    metadata: dict[str, str],
) -> str:
    explicit = _first_non_empty(
        metadata.get("job-intel:post-id"),
        metadata.get("job-intel:post_id"),
        metadata.get("post-id"),
        metadata.get("post_id"),
        None,
    )
    if explicit:
        return explicit
    identity = url or _relative_identity(path, root)
    return f"html-{sha256(identity.encode('utf-8')).hexdigest()[:16]}"


def _resolve_platform(
    *,
    path: Path,
    root: Path,
    url: str,
    metadata: dict[str, str],
    default_platform: str,
) -> str:
    explicit = _first_non_empty(
        metadata.get("job-intel:platform"),
        metadata.get("platform"),
        None,
    )
    if explicit:
        return _platform_token(explicit)

    host = urlparse(url).netloc.lower()
    for platform, host_hints in PLATFORM_HOST_HINTS.items():
        if any(hint in host for hint in host_hints):
            return platform

    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = path.name
    first_part = relative.parts[0] if isinstance(relative, Path) and relative.parts else ""
    if first_part and first_part != path.name:
        return _platform_token(first_part)
    return _platform_token(default_platform)


def _resolve_images(html_path: Path, sources: list[str]) -> tuple[list[str], list[str]]:
    images: list[str] = []
    remote_images: list[str] = []
    seen_local: set[str] = set()
    seen_remote: set[str] = set()

    for source in sources:
        resolved = _resolve_image(html_path, source)
        if resolved is None:
            if source not in seen_remote:
                remote_images.append(source)
                seen_remote.add(source)
            continue
        image_path = str(resolved)
        if image_path not in seen_local:
            images.append(image_path)
            seen_local.add(image_path)

    return images, remote_images


def _resolve_image(html_path: Path, source: str) -> Path | None:
    source = source.strip()
    if not source:
        return None

    as_path = Path(source)
    if as_path.is_absolute():
        return as_path if _is_existing_image(as_path) else None

    parsed = urlparse(source)
    if parsed.scheme in {"http", "https", "data", "blob"}:
        return None
    if parsed.scheme == "file":
        file_path = _file_url_to_path(parsed.path)
        return file_path if _is_existing_image(file_path) else None
    if parsed.scheme:
        return None

    local_part = unquote(parsed.path or source)
    candidate = (html_path.parent / local_part).resolve()
    return candidate if _is_existing_image(candidate) else None


def _is_existing_image(path: Path) -> bool:
    return path.exists() and path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES


def _file_url_to_path(path: str) -> Path:
    decoded = unquote(path)
    if re.match(r"^/[A-Za-z]:/", decoded):
        decoded = decoded[1:]
    return Path(decoded)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _relative_identity(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _platform_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip().lower())
    return token.strip("_") or "html_snapshot"


def _collapse_text(parts: list[str]) -> str:
    lines = []
    for part in parts:
        text = re.sub(r"\s+", " ", part).strip()
        if text:
            lines.append(text)
    return "\n".join(lines).strip()


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned:
                return cleaned
            continue
        return value
    return None
