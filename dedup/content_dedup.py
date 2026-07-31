from __future__ import annotations

import hashlib

from processing.cleaner import normalize_for_fingerprint
from storage.repository import Repository


def content_fingerprint(full_content: str) -> str:
    normalized = normalize_for_fingerprint(full_content)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class ContentDeduplicator:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def is_duplicate(self, fingerprint: str) -> bool:
        return self.repository.fingerprint_exists(fingerprint)

