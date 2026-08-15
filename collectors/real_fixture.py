from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from collectors.base import Collector
from models.classification import PostType
from models.raw_post import RawPost
from models.real_sample import RealSample

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
TYPE_ALIASES = {
    "infodiff": PostType.INFORMATION_GAP,
    "information_gap": PostType.INFORMATION_GAP,
    "work_condition": PostType.INFORMATION_GAP,
    "interview": PostType.INTERVIEW,
    "recruitment": PostType.RECRUITMENT,
    "offer": PostType.OFFER,
    "progress": PostType.PROGRESS,
    "other": PostType.OTHER,
}


class RealSampleLoader:
    def __init__(self, root: Path | str = "real_samples") -> None:
        self.root = Path(root)

    def load_all(self, *, include_empty: bool = True) -> list[RealSample]:
        samples: list[RealSample] = []
        for metadata_path in sorted(self.root.glob("*/*/metadata.json")):
            sample = self.load_sample(metadata_path.parent)
            if include_empty or sample.has_content:
                samples.append(sample)
        return samples

    def load_sample(self, sample_dir: Path | str) -> RealSample:
        path = Path(sample_dir)
        metadata = _read_json(path / "metadata.json")
        gold = _read_optional_json(path / "gold.json")
        type_dir = path.parent.name
        sample_name = path.name
        expected_type = _normalize_type(
            metadata.get("expected_type") or metadata.get("primary_type") or type_dir
        )
        sample_id = str(metadata.get("sample_id") or f"{type_dir}/{sample_name}")
        images = [
            str(image_path)
            for image_path in sorted(path.iterdir())
            if image_path.is_file() and image_path.suffix.lower() in IMAGE_SUFFIXES
        ]
        return RealSample(
            sample_id=sample_id,
            sample_dir=path,
            type_dir=type_dir,
            platform=str(metadata.get("platform") or "unknown"),
            url=str(metadata.get("url") or ""),
            title=str(metadata.get("title") or ""),
            text=str(metadata.get("text") or ""),
            images=images,
            publish_time=metadata.get("publish_time"),
            expected_type=expected_type,
            metadata=metadata,
            gold=gold,
        )

    def inventory(self) -> dict[str, Any]:
        samples = self.load_all(include_empty=True)
        with_images = [sample for sample in samples if sample.images]
        gold = [sample for sample in samples if sample.has_gold]
        by_type: dict[str, int] = {}
        by_platform: dict[str, int] = {}
        for sample in samples:
            key = sample.expected_type.value if sample.expected_type else sample.type_dir
            by_type[key] = by_type.get(key, 0) + 1
            by_platform[sample.platform] = by_platform.get(sample.platform, 0) + 1
        return {
            "total": len(samples),
            "by_type": by_type,
            "by_platform": by_platform,
            "with_images": len(with_images),
            "text_only": len(samples) - len(with_images),
            "with_gold": len(gold),
            "empty_or_incomplete": len([sample for sample in samples if not sample.has_content]),
        }


class RealFixtureCollector(Collector):
    def __init__(self, root: Path | str = "real_samples") -> None:
        self.loader = RealSampleLoader(root)

    def collect(self, queries: Sequence[dict[str, Any]] | None = None) -> list[RawPost]:
        del queries
        raw_posts: list[RawPost] = []
        for sample in self.loader.load_all(include_empty=False):
            raw_posts.append(sample_to_raw_post(sample))
        return raw_posts


def sample_to_raw_post(sample: RealSample) -> RawPost:
    publish_time = _parse_datetime(sample.publish_time)
    return RawPost(
        post_id=sample.sample_id,
        platform=sample.platform,
        url=sample.url,
        title=sample.title,
        author=sample.metadata.get("author"),
        publish_time=publish_time,
        crawl_time=datetime.now(timezone.utc),
        text=sample.text,
        images=sample.images,
        metadata={
            **sample.metadata,
            "sample_id": sample.sample_id,
            "sample_dir": str(sample.sample_dir),
            "expected_type": sample.expected_type.value if sample.expected_type else None,
        },
    )


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _read_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return _read_json(path)


def _normalize_type(value: Any) -> PostType | None:
    if value is None:
        return None
    key = str(value).strip()
    if not key:
        return None
    if key in TYPE_ALIASES:
        return TYPE_ALIASES[key]
    try:
        return PostType(key)
    except ValueError:
        return None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
