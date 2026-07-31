from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from models.classification import ClassificationResult, PostType
from models.interview import Interview, InterviewRound
from models.offer import Offer
from models.raw_post import RawPost
from models.recruitment import Recruitment
from models.work_condition import WorkCondition


def test_raw_post_model_requires_identifiers() -> None:
    post = RawPost(
        post_id="  p1 ",
        platform=" mock ",
        url="https://mock.local/post/1",
        title="title",
        text="body",
        crawl_time=datetime.fromisoformat("2026-07-31T10:00:00+08:00"),
    )

    assert post.post_id == "p1"
    assert post.platform == "mock"

    with pytest.raises(ValidationError):
        RawPost(post_id="", platform="mock", url="https://mock.local/post/2")


def test_classification_result_normalizes_tags() -> None:
    result = ClassificationResult(
        primary_type=PostType.OFFER,
        secondary_tags=["salary", " salary ", "", "benefit"],
        confidence=0.9,
    )

    assert result.primary_type == PostType.OFFER
    assert result.secondary_tags == ["benefit", "salary"]


def test_four_business_schemas_validate() -> None:
    recruitment = Recruitment(
        post_id="r1",
        company="字节跳动",
        job_title="推荐算法工程师",
        job_family="推荐算法",
        confidence=0.9,
    )
    interview = Interview(
        post_id="i1",
        job_title="推荐算法",
        rounds=[InterviewRound(round_number=1, round_type="一面")],
        confidence=0.9,
    )
    offer = Offer(
        post_id="o1",
        company="美团",
        salary_raw="28×15，2w sign",
        base_monthly=28000,
        salary_months=15,
        sign_on_bonus=20000,
        confidence=0.9,
    )
    work_condition = WorkCondition(
        post_id="w1",
        company="腾讯",
        work_hours_raw="10:30-20:30",
        wlb_score=6.5,
        confidence=0.9,
    )

    assert recruitment.company == "字节跳动"
    assert interview.rounds and interview.rounds[0].round_type == "一面"
    assert offer.annual_base is None
    assert work_condition.wlb_score == 6.5

