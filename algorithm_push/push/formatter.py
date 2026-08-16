from __future__ import annotations

from algorithm_push.models import DailySelection


def format_daily_questions(selection: DailySelection) -> str:
    groups = {
        "LeetCode": [
            item
            for item in selection.items
            if item.slot.startswith("leetcode_")
        ],
        "NowCoder": [
            item
            for item in selection.items
            if item.slot.startswith("nowcoder_")
        ],
        "面试补充": [
            item
            for item in selection.items
            if item.slot.startswith("interview_extra_")
        ],
    }

    lines = [f"【今日算法题 · {selection.selection_date.isoformat()}】", ""]
    question_number = 1
    for title, items in groups.items():
        lines.append(title)
        for item in items:
            lines.append(f"{question_number}. {item.question.title}")
            lines.append(item.question.url or "")
            lines.append("")
            question_number += 1
    return "\n".join(lines).rstrip()
