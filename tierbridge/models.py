"""Lesson schema: load + validate the teacher's lesson YAML."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import yaml

SCAFFOLD_PATH = Path(__file__).resolve().parent.parent / "scaffolds" / "library.json"
TIER_IDS = ("t1", "t2", "t3")
REQUIRED_FIELDS = ("subject", "topic", "objective", "success_criteria", "key_terms", "exit_ticket")
VALID_FUNCTIONS = ("concept", "define", "describe", "explain", "compare",
                   "calculate", "evaluate", "interpret")


class LessonError(ValueError):
    pass


@lru_cache(maxsize=1)
def load_scaffolds() -> dict:
    with open(SCAFFOLD_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_lesson(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        lesson = yaml.safe_load(f)
    validate_lesson(lesson)
    return lesson


def validate_lesson(lesson: dict) -> None:
    if not isinstance(lesson, dict):
        raise LessonError("lesson file must be a YAML mapping")
    missing = [f for f in REQUIRED_FIELDS if not lesson.get(f)]
    if missing:
        raise LessonError(f"missing required fields: {', '.join(missing)}")

    sc = lesson["success_criteria"]
    if not isinstance(sc, list) or not (2 <= len(sc) <= 5):
        raise LessonError("success_criteria must be a list of 2-5 items")

    for i, term in enumerate(lesson["key_terms"]):
        if not isinstance(term, dict) or "term" not in term or "definition" not in term:
            raise LessonError(f"key_terms[{i}] needs 'term' and 'definition' (optional 'zh')")

    et = lesson["exit_ticket"]
    if not isinstance(et, list) or not (3 <= len(et) <= 5):
        raise LessonError("exit_ticket must be a list of 3-5 questions")
    for i, q in enumerate(et):
        if not isinstance(q, dict) or "question" not in q or "function" not in q:
            raise LessonError(f"exit_ticket[{i}] needs 'question' and 'function'")
        if q["function"] not in VALID_FUNCTIONS:
            raise LessonError(
                f"exit_ticket[{i}].function {q['function']!r} not in {VALID_FUNCTIONS}")

    ws = lesson.get("worksheets")
    if ws is not None:
        for tid in TIER_IDS:
            tier = ws.get(tid)
            if not tier or not isinstance(tier.get("tasks"), list) or not tier["tasks"]:
                raise LessonError(f"worksheets.{tid}.tasks must be a non-empty list")
