from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date

from algorithm_push.models import Question, QuestionPool
from algorithm_push.models.selection import DailySelection, SelectionItem
from algorithm_push.registry import AlgorithmQuestionRepository
from algorithm_push.selector.config import SelectionConfig
from algorithm_push.selector.constraints import satisfies_daily_topic_constraints
from algorithm_push.selector.scoring import candidate_score


class SelectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ScoredQuestion:
    question: Question
    score: float


LEETCODE_POOLS = {QuestionPool.LEETCODE_HOT100, QuestionPool.LEETCODE_CUSTOM}
NOWCODER_POOLS = {QuestionPool.NOWCODER_HOT101}
INTERVIEW_EXTRA_POOLS = {
    QuestionPool.INTERVIEW_EXTRACTED,
    QuestionPool.INTERVIEW_MANUAL,
}


class DailySelector:
    def __init__(
        self,
        repository: AlgorithmQuestionRepository,
        *,
        config: SelectionConfig | None = None,
    ) -> None:
        self.repository = repository
        self.config = config or SelectionConfig()

    def select(
        self,
        selection_date: date,
        *,
        seed: int | None = None,
        reuse_existing: bool = True,
        persist: bool = False,
    ) -> DailySelection:
        if reuse_existing:
            existing = self.repository.get_daily_selection(selection_date)
            if existing is not None:
                return existing

        rng = random.Random(seed)
        last_selected = self.repository.last_selected_dates_by_canonical(before=selection_date)
        recent_topics = self.repository.topic_counts(
            before=selection_date,
            days=self.config.topics.recent_window_days,
        )
        scored_groups = {
            "leetcode": self._score_candidates(
                self.repository.list_active_questions_in_pools(LEETCODE_POOLS),
                selection_date=selection_date,
                last_selected=last_selected,
                recent_topics=recent_topics,
            ),
            "nowcoder": self._score_candidates(
                self.repository.list_active_questions_in_pools(NOWCODER_POOLS),
                selection_date=selection_date,
                last_selected=last_selected,
                recent_topics=recent_topics,
            ),
            "interview_extra": self._score_candidates(
                self._interview_extra_candidates(),
                selection_date=selection_date,
                last_selected=last_selected,
                recent_topics=recent_topics,
            ),
        }

        for _ in range(self.config.max_attempts):
            selected: list[SelectionItem] = []
            used_canonicals: set[str] = set()
            try:
                self._append_group(
                    selected,
                    used_canonicals,
                    scored_groups["leetcode"],
                    count=self.config.leetcode_count,
                    slot_prefix="leetcode",
                    rng=rng,
                )
                self._append_group(
                    selected,
                    used_canonicals,
                    scored_groups["nowcoder"],
                    count=self.config.nowcoder_count,
                    slot_prefix="nowcoder",
                    rng=rng,
                )
                self._append_group(
                    selected,
                    used_canonicals,
                    scored_groups["interview_extra"],
                    count=self.config.interview_extra_count,
                    slot_prefix="interview_extra",
                    rng=rng,
                )
            except SelectionError:
                continue
            if satisfies_daily_topic_constraints(
                [item.question for item in selected],
                self.config.topics,
            ):
                daily = DailySelection(selection_date=selection_date, items=selected)
                if persist:
                    self.repository.save_daily_selection(daily)
                    return self.repository.get_daily_selection(selection_date) or daily
                return daily

        raise SelectionError(
            "unable to build a daily selection that satisfies source and topic constraints"
        )

    def _interview_extra_candidates(self) -> list[Question]:
        questions = self.repository.list_active_questions_in_pools(INTERVIEW_EXTRA_POOLS)
        return [
            question
            for question in questions
            if not self.repository.canonical_has_hot_pool(question.canonical_key)
        ]

    def _score_candidates(
        self,
        questions: list[Question],
        *,
        selection_date: date,
        last_selected: dict[str, date],
        recent_topics: dict[str, int],
    ) -> list[ScoredQuestion]:
        scored: list[ScoredQuestion] = []
        for question in questions:
            score = candidate_score(
                question=question,
                selection_date=selection_date,
                last_selected_by_canonical=last_selected,
                recent_topic_counts=recent_topics,
                recency_config=self.config.recency,
                topic_config=self.config.topics,
            )
            if score > 0:
                scored.append(ScoredQuestion(question=question, score=score))
        return scored

    def _append_group(
        self,
        selected: list[SelectionItem],
        used_canonicals: set[str],
        candidates: list[ScoredQuestion],
        *,
        count: int,
        slot_prefix: str,
        rng: random.Random,
    ) -> None:
        for slot_index in range(1, count + 1):
            eligible = [
                candidate
                for candidate in candidates
                if candidate.question.canonical_key not in used_canonicals
            ]
            if not eligible:
                raise SelectionError(f"not enough eligible candidates for {slot_prefix}")
            picked = _weighted_choice(eligible, rng)
            used_canonicals.add(picked.question.canonical_key)
            selected.append(
                SelectionItem(
                    question=picked.question,
                    slot=f"{slot_prefix}_{slot_index}",
                    selected_score=picked.score,
                )
            )


def _weighted_choice(candidates: list[ScoredQuestion], rng: random.Random) -> ScoredQuestion:
    total = sum(candidate.score for candidate in candidates)
    if total <= 0:
        raise SelectionError("all candidate scores are zero")
    threshold = rng.uniform(0, total)
    cumulative = 0.0
    for candidate in candidates:
        cumulative += candidate.score
        if cumulative >= threshold:
            return candidate
    return candidates[-1]
