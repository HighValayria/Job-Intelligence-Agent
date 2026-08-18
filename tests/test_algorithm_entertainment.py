from __future__ import annotations

from datetime import date

from algorithm_push.entertainment.meme_fetcher import fetch_recent_meme_images


def test_fetch_recent_meme_images_uses_recent_threads_and_first_post_images() -> None:
    forum_html = """
    <a href="/p/1001" title="recent meme">recent meme</a>
    <span class="threadlist_reply_date">08-18</span>
    <a href="/p/1002" title="old meme">old meme</a>
    <span class="threadlist_reply_date">08-01</span>
    """
    thread_html = """
    <div id="post_content_1">
      <img class="BDE_Image" src="https://imgsa.baidu.com/forum/w%3D580/recent-1.jpg">
      <img class="BDE_Image" src="//imgsa.baidu.com/forum/w%3D580/recent-2.png">
    </div>
    <div id="post_content_2">
      <img class="BDE_Image" src="https://imgsa.baidu.com/forum/reply.jpg">
    </div>
    """

    def fetch(url: str) -> str:
        if "/f?" in url:
            return forum_html
        if "/p/1001" in url:
            return thread_html
        raise AssertionError(f"unexpected fetch: {url}")

    memes = fetch_recent_meme_images(
        limit=2,
        days=5,
        today=date(2026, 8, 18),
        fetch_text=fetch,
        shuffle=False,
    )

    assert [meme.title for meme in memes] == ["recent meme", "recent meme"]
    assert memes[0].post_date == date(2026, 8, 18)
    assert memes[0].image_url.endswith("recent-1.jpg")
    assert memes[1].image_url.startswith("https://")
