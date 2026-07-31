from __future__ import annotations

from pydantic import BaseModel

from llm.base import ExtractedResult
from models.classification import ClassificationResult, PostType
from models.interview import Interview
from models.offer import Offer
from models.recruitment import Recruitment
from models.work_condition import WorkCondition


_MODEL_BY_POST_TYPE: dict[PostType, type[BaseModel]] = {
    PostType.RECRUITMENT: Recruitment,
    PostType.INTERVIEW: Interview,
    PostType.OFFER: Offer,
    PostType.WORK_CONDITION: WorkCondition,
}


def validate_classification(value: ClassificationResult | dict) -> ClassificationResult:
    if isinstance(value, ClassificationResult):
        return value
    return ClassificationResult.model_validate(value)


def validate_extraction(post_type: PostType, value: ExtractedResult | dict) -> ExtractedResult:
    model = _MODEL_BY_POST_TYPE.get(post_type)
    if model is None:
        return None
    if isinstance(value, model):
        return value
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return model.model_validate(value)

