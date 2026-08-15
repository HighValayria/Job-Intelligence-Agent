from __future__ import annotations

import re
from datetime import date
from typing import Any


class CompanyNormalizer:
    def __init__(self, companies: list[dict[str, Any]]) -> None:
        self.companies = companies

    def normalize(self, value: str | None) -> str | None:
        if not value:
            return None
        for company in self.companies:
            aliases = set(company.get("aliases", []))
            aliases.add(company.get("canonical_name", ""))
            if value in aliases or any(alias and alias in value for alias in aliases):
                return company["canonical_name"]
        return value


class JobFamilyNormalizer:
    def __init__(self, taxonomy: dict[str, Any]) -> None:
        self.taxonomy = taxonomy

    def normalize(self, value: str | None) -> str | None:
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


class SalaryNormalizer:
    def parse_monthly(self, value: str | None) -> int | None:
        if not value:
            return None
        match = re.search(r"(\d+(?:\.\d+)?)\s*[kK千]", value)
        if match:
            return int(float(match.group(1)) * 1000)
        match = re.search(r"(\d+(?:\.\d+)?)\s*[wW万]", value)
        if match:
            return int(float(match.group(1)) * 10000)
        match = re.search(r"(\d{4,6})", value)
        if match:
            return int(match.group(1))
        return None

    def parse_months(self, value: str | None) -> int | None:
        if not value:
            return None
        match = re.search(r"[x×*]\s*(\d{1,2})", value)
        return int(match.group(1)) if match else None


class InterviewRoundNormalizer:
    ROUND_ALIASES = {
        "一面": 1,
        "初面": 1,
        "二面": 2,
        "三面": 3,
        "hr面": None,
        "hr 面": None,
        "主管面": None,
        "交叉面": None,
    }

    def normalize_round_number(self, value: str | None) -> int | None:
        if not value:
            return None
        lowered = value.lower()
        if lowered in self.ROUND_ALIASES:
            return self.ROUND_ALIASES[lowered]
        match = re.search(r"第?\s*(\d+)\s*面", value)
        return int(match.group(1)) if match else None


class DateNormalizer:
    def parse_iso_date(self, value: str | None) -> date | None:
        if not value:
            return None
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None

