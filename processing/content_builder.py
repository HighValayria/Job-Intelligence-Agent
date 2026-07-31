from __future__ import annotations

from models.raw_post import RawPost
from models.unified_content import UnifiedContent
from processing.cleaner import clean_text
from processing.ocr import OCRProvider


class ContentBuilder:
    def __init__(self, ocr_provider: OCRProvider) -> None:
        self.ocr_provider = ocr_provider

    def build(self, raw_post: RawPost) -> UnifiedContent:
        text = clean_text(raw_post.text)
        ocr_text = clean_text(
            "\n\n".join(
                result.text
                for result in (self.ocr_provider.extract(image) for image in raw_post.images)
                if result.text
            )
        )
        full_content = clean_text(
            "\n\n".join(
                part
                for part in (
                    f"标题：{raw_post.title}",
                    f"正文：{text}" if text else "",
                    f"OCR：{ocr_text}" if ocr_text else "",
                )
                if part
            )
        )
        return UnifiedContent(
            post_id=raw_post.post_id,
            platform=raw_post.platform,
            title=raw_post.title,
            text=text,
            ocr_text=ocr_text,
            full_content=full_content,
            source_images=raw_post.images,
        )

