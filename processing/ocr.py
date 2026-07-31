from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import Field

from models.common import JobIntelModel


class OCRResult(JobIntelModel):
    image: str
    text: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    provider: str = "unknown"


class OCRProvider(ABC):
    @abstractmethod
    def extract(self, image: str) -> OCRResult:
        """Extract OCR text from one image handle or path."""


class MockOCRProvider(OCRProvider):
    def __init__(self, text_by_image: dict[str, str] | None = None) -> None:
        self.text_by_image = text_by_image or _default_mock_ocr()

    def extract(self, image: str) -> OCRResult:
        text = self.text_by_image.get(image, "")
        return OCRResult(
            image=image,
            text=text,
            confidence=0.99 if text else 0.0,
            provider="mock",
        )


def _default_mock_ocr() -> dict[str, str]:
    return {
        "mock://xhs/interview/reco_algorithm_001": (
            "一面\n"
            "1. 自我介绍\n"
            "2. DIN 的 attention 是怎么做的\n"
            "3. 手撕 LRU\n\n"
            "二面\n"
            "1. LoRA 原理\n"
            "2. 推荐系统负采样\n"
            "3. 手撕 Top K"
        )
    }

