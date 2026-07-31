from __future__ import annotations

from models.raw_post import RawPost
from storage.repository import Repository


class PostDeduplicator:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def is_duplicate(self, raw_post: RawPost) -> bool:
        return self.repository.post_exists(raw_post.platform, raw_post.post_id)

