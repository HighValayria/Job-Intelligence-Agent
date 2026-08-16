from __future__ import annotations

from pathlib import Path

from algorithm_push.ingestion.manual_loader import import_questions_file
from algorithm_push.models import QuestionPool
from algorithm_push.registry import AlgorithmQuestionRepository


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_FILES = [
    (PACKAGE_ROOT / "data" / "leetcode_hot100.yaml", QuestionPool.LEETCODE_HOT100),
    (PACKAGE_ROOT / "data" / "nowcoder_hot101.yaml", QuestionPool.NOWCODER_HOT101),
    (PACKAGE_ROOT / "data" / "leetcode_custom.yaml", QuestionPool.LEETCODE_CUSTOM),
    (
        PACKAGE_ROOT / "data" / "manual_interview_questions.yaml",
        QuestionPool.INTERVIEW_MANUAL,
    ),
]


def import_default_questions(repository: AlgorithmQuestionRepository) -> int:
    total = 0
    for path, pool in DEFAULT_DATA_FILES:
        total += len(import_questions_file(repository, path, default_pool=pool))
    return total
