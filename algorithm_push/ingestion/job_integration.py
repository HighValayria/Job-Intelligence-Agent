from __future__ import annotations

import re
from dataclasses import dataclass

from algorithm_push.models import InterviewQuestionCandidate
from algorithm_push.registry import AlgorithmQuestionRepository
from models.interview import Interview, InterviewRound
from models.raw_post import RawPost


_URL_RE = re.compile(r"https?://[^\s，。；、)）]+", re.IGNORECASE)


@dataclass(frozen=True)
class JobInterviewIngestionSummary:
    mentions_seen: int
    questions_saved: int
    linked_to_hot_pool: int
    pending_without_url: int


def ingest_interview_algorithm_questions(
    repository: AlgorithmQuestionRepository,
    *,
    interview: Interview,
    raw_post: RawPost,
) -> JobInterviewIngestionSummary:
    mentions_seen = 0
    questions_saved = 0
    linked_to_hot_pool = 0
    pending_without_url = 0

    for candidate in interview_algorithm_candidates(interview, raw_post=raw_post):
        mentions_seen += 1
        result = repository.upsert_interview_question(candidate)
        if result.duplicate_of_hot_pool:
            linked_to_hot_pool += 1
        elif result.inserted_or_updated:
            questions_saved += 1
            if candidate.url is None:
                pending_without_url += 1

    return JobInterviewIngestionSummary(
        mentions_seen=mentions_seen,
        questions_saved=questions_saved,
        linked_to_hot_pool=linked_to_hot_pool,
        pending_without_url=pending_without_url,
    )


def interview_algorithm_candidates(
    interview: Interview,
    *,
    raw_post: RawPost,
) -> list[InterviewQuestionCandidate]:
    candidates: list[InterviewQuestionCandidate] = []
    for round_data in interview.rounds or []:
        round_label = _round_label(round_data)
        for raw_title in _iter_question_titles(round_data):
            title, url = _split_title_and_url(raw_title)
            if not title:
                continue
            candidates.append(
                InterviewQuestionCandidate(
                    raw_title=raw_title,
                    normalized_title=title,
                    url=url,
                    source_post_url=raw_post.url,
                    company=interview.company,
                    interview_round=round_label,
                    context=_context(interview, round_data),
                    primary_tag=_infer_primary_tag(title),
                    tags=_infer_tags(title),
                    enabled=True,
                )
            )
    return candidates


def _iter_question_titles(round_data: InterviewRound) -> list[str]:
    values: list[str] = []
    for bucket in (round_data.coding_questions, round_data.algorithm_questions):
        for value in bucket or []:
            cleaned = value.strip()
            if cleaned and cleaned not in values:
                values.append(cleaned)
    return values


def _split_title_and_url(value: str) -> tuple[str, str | None]:
    match = _URL_RE.search(value)
    if match is None:
        return value.strip(" ：:-"), None
    url = match.group(0)
    title = (value[: match.start()] + value[match.end() :]).strip(" ：:-")
    return title or value.strip(), url


def _round_label(round_data: InterviewRound) -> str | None:
    if round_data.round_type:
        return round_data.round_type
    if round_data.round_number is not None:
        return f"round_{round_data.round_number}"
    return None


def _context(interview: Interview, round_data: InterviewRound) -> str:
    parts = [
        value
        for value in [
            interview.company,
            interview.job_title,
            interview.job_family,
            _round_label(round_data),
        ]
        if value
    ]
    return " / ".join(parts)


def _infer_primary_tag(title: str) -> str:
    lowered = title.lower()
    rules = [
        (("lru", "lfu", "缓存", "cache"), "design"),
        (("top k", "topk", "堆", "k个数", "k 个数"), "heap"),
        (("二叉树", "树", "tree"), "binary_tree"),
        (("链表", "linked list"), "linked_list"),
        (("岛屿", "图", "graph", "dijkstra"), "graph"),
        (("动态规划", "dp", "区间 dp"), "dynamic_programming"),
        (("回溯", "排列", "组合", "backtracking"), "backtracking"),
        (("滑动窗口", "双指针"), "two_pointer_sliding_window"),
        (("字符串", "string"), "string"),
        (("哈希", "hash", "两数之和"), "array_hash"),
        (("贪心", "greedy"), "greedy"),
        (("并查集", "union find"), "union_find"),
    ]
    for needles, tag in rules:
        if any(needle in lowered for needle in needles):
            return tag
    return "other"


def _infer_tags(title: str) -> list[str]:
    primary = _infer_primary_tag(title)
    tags = [primary]
    lowered = title.lower()
    if "手撕" in title and "design" not in tags:
        tags.append("design")
    if "leetcode" in lowered and "other" not in tags:
        tags.append("other")
    return tags
