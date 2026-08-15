from __future__ import annotations

from abc import ABC, abstractmethod

from models.classification import ClassificationResult, PostType
from models.information_gap import InformationGap
from models.interview import Interview
from models.offer import Offer
from models.recruitment import Recruitment
from models.unified_content import UnifiedContent

ExtractedResult = Recruitment | Interview | Offer | InformationGap | None


class LLMProvider(ABC):
    @abstractmethod
    def classify(self, content: UnifiedContent) -> ClassificationResult:
        """Classify unified content into a primary post type plus secondary tags."""

    @abstractmethod
    def extract(self, content: UnifiedContent, post_type: PostType) -> ExtractedResult:
        """Extract a typed structured record from unified content."""

    @abstractmethod
    def normalize(self, result: ExtractedResult) -> ExtractedResult:
        """Normalize company names, job families, and other controlled values."""
