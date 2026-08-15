from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import AliasChoices, Field

from models.common import JobIntelModel


class OCRResult(JobIntelModel):
    image_path: str = Field(validation_alias=AliasChoices("image_path", "image"))
    text: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    provider: str = "unknown"
    status: str = "ok"
    error: str | None = None
    raw_result: Any | None = None


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
            image_path=image,
            text=text,
            confidence=0.99 if text else 0.0,
            provider="mock",
            status="ok" if text else "empty",
        )


class PaddleOCRProvider(OCRProvider):
    def __init__(self, *, lang: str = "ch") -> None:
        self.lang = lang
        self._ocr: Any | None = None

    def extract(self, image: str) -> OCRResult:
        try:
            ocr = self._get_ocr()
            raw_result = _run_paddle_ocr(ocr, image)
            lines, confidences = _parse_paddle_result(raw_result)
            text = "\n".join(lines).strip()
            confidence = (
                sum(confidences) / len(confidences) if confidences else 0.0
            )
            return OCRResult(
                image_path=image,
                text=text,
                confidence=confidence,
                provider="paddleocr",
                status="ok" if text else "empty",
                raw_result={
                    "line_count": len(lines),
                    "scores": confidences,
                },
            )
        except Exception as exc:
            return OCRResult(
                image_path=image,
                text="",
                confidence=0.0,
                provider="paddleocr",
                status="error",
                error=str(exc),
            )

    def _get_ocr(self) -> Any:
        if self._ocr is None:
            from paddleocr import PaddleOCR

            try:
                self._ocr = PaddleOCR(lang=self.lang)
            except TypeError:
                self._ocr = PaddleOCR(use_angle_cls=True, lang=self.lang)
        return self._ocr


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


def _run_paddle_ocr(ocr: Any, image: str) -> Any:
    try:
        return ocr.predict(input=image)
    except AttributeError:
        return ocr.ocr(image, cls=True)
    except TypeError:
        return ocr.ocr(image, cls=True)


def _parse_paddle_result(raw_result: Any) -> tuple[list[str], list[float]]:
    lines: list[str] = []
    confidences: list[float] = []
    for page in raw_result or []:
        if isinstance(page, dict) or hasattr(page, "get"):
            texts = list(page.get("rec_texts", []) or [])
            scores = list(page.get("rec_scores", []) or [])
            for index, text in enumerate(texts):
                if text:
                    lines.append(str(text))
                    if index < len(scores):
                        confidences.append(float(scores[index]))
            continue
        for line in page or []:
            if len(line) >= 2 and len(line[1]) >= 2:
                text, confidence = line[1][0], float(line[1][1])
                if text:
                    lines.append(str(text))
                    confidences.append(confidence)
    return lines, confidences
