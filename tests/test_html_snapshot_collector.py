from __future__ import annotations

from pathlib import Path

from collectors.html_snapshot import (
    HtmlSnapshotCollector,
    inventory_html_snapshots,
    parse_html_snapshot,
    render_html_snapshot_inventory,
)
from scheduler.provider_factory import create_collector


def test_parse_html_snapshot_extracts_post_fields_and_local_images(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox" / "html"
    page_dir = inbox / "nowcoder"
    image_dir = page_dir / "assets"
    image_dir.mkdir(parents=True)
    image_path = image_dir / "screen.png"
    image_path.write_bytes(b"fake-image")
    html_path = page_dir / "post.html"
    html_path.write_text(
        """
        <html data-platform="nowcoder">
          <head>
            <title>Backend interview note</title>
            <link rel="canonical" href="https://www.nowcoder.com/discuss/123" />
            <meta name="job-intel:post-id" content="nc-123" />
            <meta name="author" content="alice" />
            <meta property="article:published_time" content="2026-08-01T12:00:00+08:00" />
            <script>hidden tracking text</script>
          </head>
          <body>
            <h1>Backend interview note</h1>
            <p>Round one asked cache and message queue questions.</p>
            <img src="assets/screen.png" />
            <img src="https://cdn.example.test/remote.png" />
          </body>
        </html>
        """,
        encoding="utf-8",
    )

    raw_post = parse_html_snapshot(html_path, root=inbox)

    assert raw_post.post_id == "nc-123"
    assert raw_post.platform == "nowcoder"
    assert raw_post.url == "https://www.nowcoder.com/discuss/123"
    assert raw_post.title == "Backend interview note"
    assert raw_post.author == "alice"
    assert raw_post.publish_time is not None
    assert "Round one asked cache" in raw_post.text
    assert "hidden tracking text" not in raw_post.text
    assert raw_post.images == [str(image_path.resolve())]
    assert raw_post.metadata["source_type"] == "html_snapshot"
    assert raw_post.metadata["remote_images"] == ["https://cdn.example.test/remote.png"]


def test_html_snapshot_collector_deduplicates_same_canonical_url(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox" / "html" / "xiaohongshu"
    inbox.mkdir(parents=True)
    html = """
    <html>
      <head>
        <meta property="og:url" content="https://www.xiaohongshu.com/explore/abc" />
        <title>Offer note</title>
      </head>
      <body>Offer package and timeline.</body>
    </html>
    """
    (inbox / "first.html").write_text(html, encoding="utf-8")
    (inbox / "second.html").write_text(html, encoding="utf-8")

    collector = HtmlSnapshotCollector(tmp_path / "inbox" / "html")
    posts = collector.collect()

    assert len(posts) == 1
    assert posts[0].platform == "xiaohongshu"
    assert posts[0].post_id.startswith("html-")


def test_parse_html_snapshot_allows_missing_url(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox" / "html" / "nowcoder"
    inbox.mkdir(parents=True)
    html_path = inbox / "no-url.html"
    html_path.write_text(
        """
        <html>
          <head><title>No URL note</title></head>
          <body>Useful visible text without a canonical URL.</body>
        </html>
        """,
        encoding="utf-8",
    )

    raw_post = parse_html_snapshot(html_path, root=tmp_path / "inbox" / "html")

    assert raw_post.url == ""
    assert raw_post.platform == "nowcoder"
    assert raw_post.post_id.startswith("html-")
    assert "Useful visible text" in raw_post.text


def test_html_snapshot_inventory_reports_warnings_and_previews(tmp_path: Path) -> None:
    inbox = tmp_path / "inbox" / "html"
    xhs = inbox / "xiaohongshu"
    nowcoder = inbox / "nowcoder"
    xhs.mkdir(parents=True)
    nowcoder.mkdir(parents=True)
    image_path = xhs / "screen.png"
    image_path.write_bytes(b"fake")
    duplicated = """
    <html>
      <head>
        <meta property="og:url" content="https://www.xiaohongshu.com/explore/abc" />
        <title>Offer note</title>
      </head>
      <body><p>Offer package and timeline.</p><img src="screen.png" /></body>
    </html>
    """
    (xhs / "first.html").write_text(duplicated, encoding="utf-8")
    (xhs / "second.html").write_text(duplicated, encoding="utf-8")
    (nowcoder / "missing-url.html").write_text(
        "<html><head><title>Interview note</title></head><body></body></html>",
        encoding="utf-8",
    )

    inventory = inventory_html_snapshots(inbox)
    rendered_limited = render_html_snapshot_inventory(inventory, limit=2)
    rendered_all = render_html_snapshot_inventory(inventory, limit=3)

    assert inventory.total_files == 3
    assert inventory.collected_count == 2
    assert inventory.duplicate_count == 1
    assert inventory.by_platform == {"nowcoder": 1, "xiaohongshu": 1}
    assert inventory.local_image_count == 2
    assert inventory.empty_text_count == 1
    assert inventory.missing_url_count == 1
    assert "duplicate_post_id_in_inbox" in rendered_all
    assert "missing_url" in rendered_all
    assert "... 1 more snapshot(s)" in rendered_limited


def test_provider_factory_creates_html_snapshot_collector(tmp_path: Path) -> None:
    collector = create_collector("html-snapshot", inbox_dir=tmp_path)

    assert isinstance(collector, HtmlSnapshotCollector)
