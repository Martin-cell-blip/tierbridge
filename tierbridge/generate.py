"""Build the tiered worksheet pack from a lesson.

Two modes:
  * authored  - the lesson YAML carries `worksheets:` written by the teacher (or by
                a previous AI run the teacher has reviewed). Used as-is.
  * template  - no worksheets in the YAML: build scaffolded task shells from the
                objective, success criteria, key terms and sentence-frame library.
                Fully offline; the teacher fills content gaps marked ____.

Optional AI enrichment (TIERBRIDGE_API_KEY) drafts tier tasks from the source
text; output is validated and always marked for teacher review.

Invariant enforced everywhere: all three tiers share the SAME objective and the
SAME success criteria and the SAME exit-ticket questions - only the scaffolding
differs. That is what makes mastery comparable across tiers.
"""
from __future__ import annotations

from .models import TIER_IDS, load_scaffolds


def _frames_for(function: str, tier: str) -> list[str]:
    frames = load_scaffolds()["sentence_frames"].get(function, {})
    return frames.get(tier, [])


def build_exit_ticket(lesson: dict) -> list[dict]:
    """Same questions for every tier; t1/t2 get frames, t1 also flags glossary use."""
    out = []
    for i, q in enumerate(lesson["exit_ticket"], 1):
        out.append({
            "n": i,
            "question": q["question"],
            "function": q["function"],
            "answer_note": q.get("answer_note", ""),
            "frames": {
                "t1": _frames_for(q["function"], "t1"),
                "t2": _frames_for(q["function"], "t2"),
                "t3": [],
            },
        })
    return out


def _template_tasks(lesson: dict, tier: str) -> list[dict]:
    """Offline task shells derived from success criteria + frames."""
    tasks = []
    for i, criterion in enumerate(lesson["success_criteria"], 1):
        function = lesson["exit_ticket"][min(i - 1, len(lesson["exit_ticket"]) - 1)]["function"]
        frames = _frames_for(function, tier)
        tasks.append({
            "title": f"Task {i}: {criterion}",
            "instructions": "[teacher: add the task prompt for this criterion]",
            "frames": frames,
            "template_shell": True,
        })
    if tier == "t3":
        tasks.append({
            "title": "Challenge: transfer",
            "instructions": "[teacher: add a transfer question applying today's objective to a new context]",
            "frames": [],
            "template_shell": True,
        })
    return tasks


def build_pack(lesson: dict) -> dict:
    scaffolds = load_scaffolds()
    authored = lesson.get("worksheets") is not None
    tiers = {}
    for tid in TIER_IDS:
        meta = scaffolds["tiers"][tid]
        if authored:
            tasks = [dict(t) for t in lesson["worksheets"][tid]["tasks"]]
        else:
            tasks = _template_tasks(lesson, tid)
        tiers[tid] = {
            "id": tid,
            "name": meta["name"],
            "audience": meta["audience"],
            "principle": meta["principle"],
            "tasks": tasks,
            "glossary": tid != "t3",           # t1 bilingual, t2 English-only, t3 none
            "glossary_bilingual": tid == "t1",
            "teacher_moves": scaffolds["teacher_moves"][tid],
        }
    return {
        "lesson": lesson,
        "mode": "authored" if authored else "template",
        "tiers": tiers,
        "exit_ticket": build_exit_ticket(lesson),
        "fading_note": scaffolds["teacher_moves"]["fading"],
    }


# ---------------------------------------------------------------- AI enrichment

ENRICH_SYSTEM = """You write tiered classroom tasks for an English-medium lesson in a bilingual school.
Rules:
1. All tiers pursue the SAME learning objective and success criteria. Never simplify the thinking for tier 1 - only the language.
2. Tier 1 tasks embed the given sentence starters and refer students to the glossary.
3. Tier 3 adds one transfer/challenge task.
4. Each task instruction is under 60 words, classroom-ready, in plain English.
Respond ONLY with JSON: {"t1": {"tasks": [{"title": "...", "instructions": "...", "frames": ["..."]}]}, "t2": {...}, "t3": {...}}
3-4 tasks per tier."""


def validate_enriched(payload: dict) -> list[str]:
    problems = []
    for tid in TIER_IDS:
        tier = payload.get(tid)
        if not tier or not isinstance(tier.get("tasks"), list) or not (2 <= len(tier["tasks"]) <= 5):
            problems.append(f"{tid}: needs 2-5 tasks")
            continue
        for j, t in enumerate(tier["tasks"]):
            if not t.get("title") or not t.get("instructions"):
                problems.append(f"{tid}.tasks[{j}]: title and instructions required")
            elif len(t["instructions"].split()) > 70:
                problems.append(f"{tid}.tasks[{j}]: instructions over 70 words")
    if not problems:
        t3_titles = " ".join(t.get("title", "").lower() for t in payload["t3"]["tasks"])
        if "challenge" not in t3_titles and "transfer" not in t3_titles:
            problems.append("t3: must include a challenge/transfer task")
    return problems


def enrich_with_ai(lesson: dict, chat_fn) -> dict:
    """Return a lesson copy whose worksheets were drafted by the model (marked for review)."""
    import json as _json
    frames_hint = {q["function"]: _frames_for(q["function"], "t1") for q in lesson["exit_ticket"]}
    user = (
        f"Subject: {lesson['subject']}\nTopic: {lesson['topic']}\n"
        f"Objective: {lesson['objective']}\n"
        f"Success criteria: {'; '.join(lesson['success_criteria'])}\n"
        f"Key terms: {', '.join(t['term'] for t in lesson['key_terms'])}\n"
        f"Tier-1 sentence starters available: {_json.dumps(frames_hint)}\n"
        f"Source text:\n{lesson.get('source_text', '(none)')}"
    )
    raw = chat_fn([{"role": "system", "content": ENRICH_SYSTEM},
                   {"role": "user", "content": user}])
    from .llm import extract_json
    payload = extract_json(raw)
    problems = validate_enriched(payload)
    if problems:
        raise ValueError("AI worksheet draft rejected: " + "; ".join(problems[:5]))
    enriched = dict(lesson)
    enriched["worksheets"] = {tid: {"tasks": payload[tid]["tasks"]} for tid in TIER_IDS}
    enriched["ai_drafted"] = True
    return enriched
