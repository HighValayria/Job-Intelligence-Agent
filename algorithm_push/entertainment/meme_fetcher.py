from __future__ import annotations

import html
import random
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable


DEFAULT_FORUM = "meme图"
DEFAULT_BASE_URL = "https://tieba.baidu.com"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


@dataclass(frozen=True)
class MemeImage:
    image_url: str
    thread_url: str
    title: str
    post_date: date | None = None


FetchText = Callable[[str], str]


def fetch_recent_meme_images(
    *,
    limit: int = 4,
    days: int = 5,
    forum: str = DEFAULT_FORUM,
    today: date | None = None,
    fetch_text: FetchText | None = None,
    shuffle: bool = True,
) -> list[MemeImage]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    if days <= 0:
        raise ValueError("days must be positive")

    current_day = today or date.today()
    cutoff = current_day - timedelta(days=days - 1)
    fetch = fetch_text or _fetch_text
    candidates = _parse_forum_threads(
        fetch(_forum_url(forum)),
        today=current_day,
        cutoff=cutoff,
    )
    if shuffle:
        random.shuffle(candidates)

    images: list[MemeImage] = []
    seen_urls: set[str] = set()
    for thread in candidates:
        try:
            thread_html = fetch(thread["url"])
        except Exception:
            continue
        for image_url in _parse_first_post_images(thread_html):
            if image_url in seen_urls:
                continue
            seen_urls.add(image_url)
            images.append(
                MemeImage(
                    image_url=image_url,
                    thread_url=thread["url"],
                    title=thread["title"],
                    post_date=thread["date"],
                )
            )
            if len(images) >= limit:
                return images
    return images


def _forum_url(forum: str) -> str:
    query = urllib.parse.urlencode({"kw": forum, "ie": "utf-8"})
    return f"{DEFAULT_BASE_URL}/f?{query}"


def _fetch_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Referer": DEFAULT_BASE_URL,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"tieba request failed: {exc.code} {body[:200]}") from exc


def _parse_forum_threads(
    page_html: str,
    *,
    today: date,
    cutoff: date,
) -> list[dict[str, object]]:
    threads: list[dict[str, object]] = []
    seen: set[str] = set()
    for match in re.finditer(r'href="(?P<href>/p/\d+)[^"]*"(?P<attrs>[^>]*)>', page_html):
        href = html.unescape(match.group("href"))
        if href in seen:
            continue
        seen.add(href)
        window = page_html[match.start() : min(len(page_html), match.end() + 2200)]
        title = _extract_title(match.group("attrs"), window)
        post_date = _extract_post_date(window, today=today)
        if post_date is not None and post_date < cutoff:
            continue
        threads.append(
            {
                "url": urllib.parse.urljoin(DEFAULT_BASE_URL, href),
                "title": title or "贴吧 meme 图",
                "date": post_date,
            }
        )
    return threads


def _extract_title(attrs: str, window: str) -> str:
    title_match = re.search(r'title="([^"]+)"', attrs)
    if title_match:
        return _clean_text(title_match.group(1))
    text_match = re.search(r'class="[^"]*j_th_tit[^"]*"[^>]*>(.*?)</a>', window, re.S)
    if text_match:
        return _clean_text(text_match.group(1))
    return ""


def _extract_post_date(window: str, *, today: date) -> date | None:
    patterns = [
        r'(\d{4})-(\d{1,2})-(\d{1,2})(?:\s+\d{1,2}:\d{2})?',
        r'(?<!\d)(\d{1,2})-(\d{1,2})(?:\s+\d{1,2}:\d{2})?(?!\d)',
    ]
    if "今天" in window:
        return today
    if "昨天" in window:
        return today - timedelta(days=1)
    for pattern in patterns:
        match = re.search(pattern, window)
        if not match:
            continue
        groups = match.groups()
        try:
            if len(groups) == 3:
                return date(int(groups[0]), int(groups[1]), int(groups[2]))
            candidate = date(today.year, int(groups[0]), int(groups[1]))
            if candidate > today + timedelta(days=1):
                candidate = date(today.year - 1, candidate.month, candidate.day)
            return candidate
        except ValueError:
            continue
    return None


def _parse_first_post_images(thread_html: str) -> list[str]:
    blocks = re.findall(
        r'<div[^>]+id="post_content_\d+"[^>]*>(.*?)</div>',
        thread_html,
        flags=re.S | re.I,
    )
    search_area = blocks[0] if blocks else thread_html[: min(len(thread_html), 20000)]
    urls: list[str] = []
    for match in re.finditer(r'<img[^>]+(?:class="[^"]*BDE_Image[^"]*"[^>]+)?src="([^"]+)"', search_area, re.I):
        image_url = html.unescape(match.group(1))
        if _looks_like_meme_image(image_url):
            urls.append(_normalize_image_url(image_url))
    return urls


def _looks_like_meme_image(url: str) -> bool:
    lowered = url.lower()
    if "tb2.bdstatic.com" in lowered:
        return False
    return any(token in lowered for token in (".jpg", ".jpeg", ".png", ".webp", "hiphotos"))


def _normalize_image_url(url: str) -> str:
    if url.startswith("//"):
        return "https:" + url
    return url


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", value))).strip()
