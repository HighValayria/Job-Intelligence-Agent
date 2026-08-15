from __future__ import annotations

from models.raw_post import RawPost
from models.unified_content import ContentSegment, UnifiedContent
from processing.cleaner import clean_text
from processing.ocr import OCRProvider


class ContentBuilder:
    def __init__(self, ocr_provider: OCRProvider) -> None:
        self.ocr_provider = ocr_provider

    def build(self, raw_post: RawPost) -> UnifiedContent:
        text = clean_text(raw_post.text)
        segments = [
            ContentSegment(
                source="metadata",
                text=clean_text(
                    "\n".join(
                        [
                            f"post_id: {raw_post.post_id}",
                            f"platform: {raw_post.platform}",
                            f"source_url: {raw_post.url}",
                        ]
                    )
                ),
                metadata={
                    "post_id": raw_post.post_id,
                    "platform": raw_post.platform,
                    "source_url": raw_post.url,
                },
            ),
            ContentSegment(source="title", text=raw_post.title, metadata={}),
        ]
        if text:
            segments.append(ContentSegment(source="text", text=text, metadata={}))

        ocr_results = [
            self.ocr_provider.extract(image).model_dump(mode="json")
            for image in raw_post.images
        ]
        for index, result in enumerate(ocr_results, start=1):
            segment_text = clean_text(result.get("text", ""))
            segment_status = result.get("status", "unknown")
            if segment_text:
                segments.append(
                    ContentSegment(
                        source=f"image_{index}_ocr",
                        text=segment_text,
                        metadata={
                            "image_path": result.get("image_path"),
                            "confidence": result.get("confidence"),
                            "status": segment_status,
                            "provider": result.get("provider"),
                        },
                    )
                )
            elif segment_status != "ok":
                segments.append(
                    ContentSegment(
                        source=f"image_{index}_ocr",
                        text="",
                        metadata={
                            "image_path": result.get("image_path"),
                            "confidence": result.get("confidence"),
                            "status": segment_status,
                            "error": result.get("error"),
                            "provider": result.get("provider"),
                        },
                    )
                )

        ocr_text = clean_text(
            "\n\n".join(
                result.get("text", "") for result in ocr_results if result.get("text")
            )
        )
        full_content = "\n\n".join(
            f"[{segment.source}]\n{segment.text}".strip()
            for segment in segments
            if segment.text or segment.source.startswith("image_")
        )
        full_content = clean_text(full_content)
        if not full_content:
            full_content = clean_text(
                "\n\n".join(part for part in (raw_post.title, text, ocr_text) if part)
            )
        return UnifiedContent(
            post_id=raw_post.post_id,
            platform=raw_post.platform,
            title=raw_post.title,
            text=text,
            ocr_text=ocr_text,
            full_content=full_content,
            source_images=raw_post.images,
            segments=segments,
            ocr_results=ocr_results,
        )
