from __future__ import annotations

from datetime import date
from typing import Any

from llm.base import ExtractedResult, LLMProvider
from models.classification import ClassificationResult, PostType
from models.common import EvidenceValue
from models.information_gap import InformationGap
from models.interview import Interview, InterviewRound
from models.offer import Offer
from models.recruitment import Recruitment
from models.unified_content import UnifiedContent


class MockLLMProvider(LLMProvider):
    def __init__(
        self,
        *,
        companies: list[dict[str, Any]] | None = None,
        taxonomy: dict[str, Any] | None = None,
    ) -> None:
        self.companies = companies or []
        self.taxonomy = taxonomy or {}

    def classify(self, content: UnifiedContent) -> ClassificationResult:
        text = content.full_content.lower()
        if _contains(
            text,
            (
                "工作体验",
                "wlb",
                "下班",
                "加班",
                "on-call",
                "信息差",
                "避坑",
                "泡池子",
                "hc",
                "转正率",
            ),
        ):
            return ClassificationResult(
                primary_type=PostType.INFORMATION_GAP,
                secondary_tags=["team", "work_hours"],
                confidence=0.92,
                evidence=["工作体验", "WLB", "下班", "信息差"],
            )
        if _contains(text, ("offer", "薪资", "sign", "总包")):
            return ClassificationResult(
                primary_type=PostType.OFFER,
                secondary_tags=["salary", "benefit"],
                confidence=0.95,
                evidence=["offer", "薪资 raw"],
            )
        if _contains(text, ("面经", "一面", "二面", "手撕")):
            return ClassificationResult(
                primary_type=PostType.INTERVIEW,
                secondary_tags=["algorithm", "ocr"],
                confidence=0.94,
                evidence=["面经", "一面", "二面"],
            )
        if _contains(text, ("招聘", "校招", "内推", "投递")):
            return ClassificationResult(
                primary_type=PostType.RECRUITMENT,
                secondary_tags=["campus", "referral"],
                confidence=0.96,
                evidence=["校招", "内推", "投递"],
            )
        return ClassificationResult(
            primary_type=PostType.OTHER,
            secondary_tags=[],
            confidence=0.3,
            evidence=[],
            needs_review=True,
        )

    def extract(self, content: UnifiedContent, post_type: PostType) -> ExtractedResult:
        if post_type == PostType.RECRUITMENT:
            return self._extract_recruitment(content)
        if post_type == PostType.INTERVIEW:
            return self._extract_interview(content)
        if post_type == PostType.OFFER:
            return self._extract_offer(content)
        if post_type in {PostType.INFORMATION_GAP, PostType.WORK_CONDITION}:
            return self._extract_information_gap(content)
        return None

    def normalize(self, result: ExtractedResult) -> ExtractedResult:
        if result is None:
            return None
        updates: dict[str, Any] = {}
        company = getattr(result, "company", None)
        if company:
            updates["company"] = self._standardize_company(company)
        job_title = getattr(result, "job_title", None)
        job_family = getattr(result, "job_family", None)
        normalized_family = self._standardize_job_family(job_title or job_family)
        if normalized_family:
            updates["job_family"] = normalized_family
        return result.model_copy(update=updates)

    def _extract_recruitment(self, content: UnifiedContent) -> Recruitment:
        return Recruitment(
            post_id=content.post_id,
            company="字节跳动",
            company_type="互联网",
            department="商业化团队",
            job_title="推荐算法工程师",
            job_family="推荐算法",
            job_type="校招",
            recruitment_batch="2026 校招",
            graduation_year=2026,
            education_requirement="本科及以上",
            major_requirement="计算机、软件工程、人工智能相关",
            city="北京/上海",
            skills=["Python", "机器学习", "推荐系统", "SQL"],
            responsibilities=["推荐排序模型优化", "用户理解", "实验分析"],
            requirements=["本科及以上", "计算机相关专业优先"],
            headcount=None,
            application_start=None,
            application_deadline=date(2026, 9, 30),
            application_method="官网投递或内推",
            official_url="https://jobs.example.com/bytedance/reco",
            referral_code="BYTEDANCE2026",
            confidence=0.92,
            needs_review=False,
            field_evidence={
                "company": _evidence("字节跳动", "字节跳动", "字节跳动商业化团队"),
                "job_title": _evidence("推荐算法工程师", "推荐算法工程师", "推荐算法工程师岗位"),
                "application_deadline": _evidence(
                    "截止 2026-09-30", "2026-09-30", "截止 2026-09-30"
                ),
                "referral_code": _evidence(
                    "BYTEDANCE2026", "BYTEDANCE2026", "内推码 BYTEDANCE2026"
                ),
            },
        )

    def _extract_interview(self, content: UnifiedContent) -> Interview:
        return Interview(
            post_id=content.post_id,
            company=None,
            department=None,
            job_title="推荐算法",
            job_family="推荐算法",
            recruitment_type=None,
            interview_date=None,
            rounds=[
                InterviewRound(
                    round_number=1,
                    round_type="一面",
                    duration=None,
                    self_intro=True,
                    project_questions=None,
                    basic_questions=["DIN 的 attention 是怎么做的"],
                    system_design_questions=None,
                    coding_questions=["手撕 LRU"],
                    algorithm_questions=["DIN attention"],
                    scenario_questions=None,
                    behavior_questions=None,
                    interviewer_focus=["推荐系统", "基础算法"],
                    difficulty=None,
                    result=None,
                ),
                InterviewRound(
                    round_number=2,
                    round_type="二面",
                    duration=None,
                    self_intro=None,
                    project_questions=None,
                    basic_questions=["LoRA 原理", "推荐系统负采样"],
                    system_design_questions=None,
                    coding_questions=["手撕 Top K"],
                    algorithm_questions=["Top K", "负采样"],
                    scenario_questions=None,
                    behavior_questions=None,
                    interviewer_focus=["LLM", "推荐系统", "算法题"],
                    difficulty=None,
                    result=None,
                ),
            ],
            confidence=0.9,
            needs_review=True,
            field_evidence={
                "rounds": _evidence(
                    content.ocr_text,
                    "2 rounds",
                    "OCR 中包含一面、二面和题目清单",
                    confidence=0.9,
                )
            },
        )

    def _extract_offer(self, content: UnifiedContent) -> Offer:
        return Offer(
            post_id=content.post_id,
            company="美团",
            department="到店",
            job_title="后端开发",
            job_family="后端",
            city="北京",
            offer_level="L6",
            offer_tier=None,
            base_monthly=28000,
            salary_months=15,
            annual_base=420000,
            performance_bonus=None,
            sign_on_bonus=20000,
            stock=None,
            allowance="餐补每天 30",
            estimated_total_comp=440000,
            probation_salary=None,
            probation_period=None,
            housing=None,
            meal="餐补每天 30",
            transport=None,
            insurance=None,
            provident_fund="全额",
            annual_leave="10 天",
            offer_date=date(2026, 7, 15),
            deadline=date(2026, 8, 1),
            accepted=False,
            salary_raw="28×15，2w sign，绩效奖金另算",
            benefit_raw="公积金按全额，餐补每天 30，年假 10 天",
            confidence=0.93,
            needs_review=False,
            field_evidence={
                "base_monthly": _evidence("28×15", 28000, "薪资 raw：28×15"),
                "salary_months": _evidence("28×15", 15, "薪资 raw：28×15"),
                "sign_on_bonus": _evidence("2w sign", 20000, "2w sign"),
                "accepted": _evidence("还没接", False, "还没接"),
            },
        )

    def _extract_information_gap(self, content: UnifiedContent) -> InformationGap:
        return InformationGap(
            post_id=content.post_id,
            company="腾讯",
            department="腾讯云",
            job_title=None,
            job_family="数据开发",
            city="深圳",
            base_monthly=None,
            salary_months=None,
            annual_total_comp=None,
            bonus=None,
            stock=None,
            salary_raw=None,
            start_time="10:30",
            end_time_typical="20:30",
            end_time_extreme="23:00",
            work_hours_raw="一般 10:30 上班，20:30 左右下班，月底项目紧会到 23 点",
            overtime_frequency="月底项目紧时较高",
            weekend_work="偶尔上线",
            on_call="轮值",
            annual_leave=None,
            canteen="食堂不错",
            meal_allowance=None,
            housing=None,
            transport="班车",
            insurance=None,
            provident_fund=None,
            management="管理规范",
            team_atmosphere="稳定",
            business_outlook="业务成熟",
            promotion="偏慢",
            job_stability="业务成熟",
            layoff_risk=None,
            headcount_status=None,
            headcount_estimate=None,
            hiring_difficulty=None,
            conversion_rate=None,
            offer_approval=None,
            hiring_process_status=None,
            pool_status=None,
            pros=["业务成熟", "管理规范", "食堂不错", "有班车"],
            cons=["需求节奏波动大", "晋升偏慢"],
            warnings=None,
            recommendation=None,
            raw_information=content.text,
            topics=["benefit", "stability", "team", "wlb"],
            wlb_score=6.5,
            overall_sentiment="中性偏正",
            confidence=0.91,
            needs_review=False,
            field_evidence={
                "work_hours_raw": _evidence(
                    "10:30 上班，20:30 左右下班，月底到 23 点",
                    "10:30-20:30, extreme 23:00",
                    "一般 10:30 上班，20:30 左右下班，月底项目紧会到 23 点",
                ),
                "wlb_score": _evidence("6.5/10", 6.5, "主观 WLB 6.5/10"),
            },
        )

    def _standardize_company(self, value: str) -> str:
        for company in self.companies:
            aliases = set(company.get("aliases", []))
            aliases.add(company.get("canonical_name", ""))
            if value in aliases or any(alias and alias in value for alias in aliases):
                return company["canonical_name"]
        return value

    def _standardize_job_family(self, value: str | None) -> str | None:
        if not value:
            return None
        aliases = self.taxonomy.get("aliases", {})
        if value in aliases:
            return aliases[value]
        for alias, family in aliases.items():
            if alias in value:
                return family
        for family in self.taxonomy.get("job_families", []):
            if family in value:
                return family
        return "其他"


def _contains(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle.lower() in text for needle in needles)


def _evidence(
    raw_value: Any,
    normalized_value: Any,
    evidence: str,
    *,
    confidence: float = 0.95,
) -> EvidenceValue:
    return EvidenceValue(
        raw_value=raw_value,
        normalized_value=normalized_value,
        confidence=confidence,
        evidence=evidence,
    )
