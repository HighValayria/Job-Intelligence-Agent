from __future__ import annotations

from pathlib import Path
from typing import Any

from algorithm_push.models import QuestionInput, QuestionPool
from algorithm_push.registry import AlgorithmQuestionRepository


def load_questions_file(
    path: Path | str,
    *,
    default_pool: QuestionPool | str | None = None,
) -> list[QuestionInput]:
    payload = _load_yaml(path)
    raw_questions = payload.get("questions", payload if isinstance(payload, list) else [])
    if not isinstance(raw_questions, list):
        raise ValueError(f"questions file must contain a list: {path}")

    questions: list[QuestionInput] = []
    for raw in raw_questions:
        if not isinstance(raw, dict):
            raise ValueError(f"question entry must be an object: {raw!r}")
        data: dict[str, Any] = dict(raw)
        if default_pool is not None and "pool" not in data:
            data["pool"] = default_pool
        questions.append(QuestionInput.model_validate(data))
    return questions


def import_questions_file(
    repository: AlgorithmQuestionRepository,
    path: Path | str,
    *,
    default_pool: QuestionPool | str | None = None,
) -> list[str]:
    question_ids: list[str] = []
    for question in load_questions_file(path, default_pool=default_pool):
        saved = repository.upsert_question(question)
        question_ids.append(saved.question_id)
    return question_ids


def _load_yaml(path: Path | str) -> Any:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    try:
        import yaml
    except ModuleNotFoundError:
        return _load_simple_questions_yaml(text)
    return yaml.safe_load(text) or {}


def _load_simple_questions_yaml(text: str) -> dict[str, Any]:
    questions: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    current_key: str | None = None

    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        line = raw_line.rstrip()
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if stripped == "questions: []":
            return {"questions": []}
        if stripped == "questions:":
            continue
        if indent > 2 and stripped.startswith("-"):
            if current is None or current_key is None:
                raise ValueError(f"list item without a key: {stripped}")
            current.setdefault(current_key, []).append(_parse_scalar(stripped[1:].strip()))
            continue
        if stripped.startswith("- "):
            if current is not None:
                questions.append(current)
            current = {}
            current_key = None
            remainder = stripped[2:].strip()
            if remainder:
                key, value = _split_key_value(remainder)
                current[key] = _parse_scalar(value)
            continue
        if current is None:
            continue
        key, value = _split_key_value(stripped)
        if value == "":
            current[key] = []
            current_key = key
        else:
            current[key] = _parse_scalar(value)
            current_key = None

    if current is not None:
        questions.append(current)
    return {"questions": questions}


def _split_key_value(value: str) -> tuple[str, str]:
    key, separator, raw_value = value.partition(":")
    if not separator:
        raise ValueError(f"expected key/value line: {value}")
    return key.strip(), raw_value.strip()


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(part.strip()) for part in inner.split(",")]
    if value in {"true", "false"}:
        return value == "true"
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value
