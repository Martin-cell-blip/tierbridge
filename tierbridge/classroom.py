"""Class persistence - turns single-lesson tools into an instructional record:

    class init  -> roster (student + EAL flag)
    class record-> one lesson session: results + auto-assignment (vs previous
                   lesson) + teacher overrides + gap snapshot (incl. by question
                   function when the lesson file is given)
    class trend -> cross-lesson report: per-student tier/mastery timeline with
                   movement rationale, class gap series, convergence verdict

Storage: one transparent class.json per class directory. No database.
The system must be able to answer two questions:
  1. Why did this student move (or not move) tier?   -> per-lesson notes + overrides
  2. Is the EAL gap converging under our teaching?   -> gap series + by-function trend
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from .assign import TIER_NAMES, TIER_ORDER, assign
from .gap import GROUPS, analyze
from .models import VALID_FUNCTIONS, load_lesson

CONVERGENCE_BAND_PP = 3.0

# The product principle, in code (v0.3.3):
TIER_PRINCIPLE = ("Tier determines challenge level; "
                  "skill profile determines what happens inside the tier.")

# skill bands on per-function scores
SECURE_AT, DEVELOPING_AT = 0.75, 0.4
NEXT_MOVES = {
    "concept": "re-anchor core definitions with a quick concept check before new content",
    "calculate": "worked example, then faded practice of the calculation routine",
    "interpret": ("targeted interpretation task on results the student can already "
                  "compute, with reduced calculation load"),
    "define": "re-anchor core definitions with a quick concept check before new content",
    "explain": "guided because-chains: student completes cause-effect steps aloud before writing",
    "evaluate": "structured judgement frame: criterion, then weigh one cost against one benefit",
    "describe": "describe-from-model task: student narrates a completed example first",
    "compare": "side-by-side comparison table before free-form contrast",
    "_foundational": ("foundations first: re-teach the core concept with scaffolds "
                      "before calculation and interpretation"),
}


class ClassError(ValueError):
    pass


# ---------------------------------------------------------------- roster / init

def load_roster(path: str | Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "student" not in reader.fieldnames or "eal" not in reader.fieldnames:
            raise ClassError("roster CSV needs columns: student, eal (1/0)")
        roster = []
        seen = set()
        for i, row in enumerate(reader):
            name = row["student"].strip()
            if not name:
                raise ClassError(f"roster row {i + 2}: empty student name")
            if name in seen:
                raise ClassError(f"roster row {i + 2}: duplicate student {name!r}")
            seen.add(name)
            eal_raw = row["eal"].strip().lower()
            if eal_raw not in ("0", "1", "eal", "non-eal", "true", "false"):
                raise ClassError(f"roster row {i + 2}: eal must be 1/0, got {row['eal']!r}")
            roster.append({"student": name, "eal": eal_raw in ("1", "eal", "true")})
    if not roster:
        raise ClassError("roster is empty")
    return roster


def _class_path(class_dir: str | Path) -> Path:
    return Path(class_dir) / "class.json"


def init_class(name: str, roster_csv: str | Path, class_dir: str | Path) -> dict:
    class_dir = Path(class_dir)
    if _class_path(class_dir).exists():
        raise ClassError(f"class already exists: {_class_path(class_dir)}")
    cls = {
        "name": name,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "roster": load_roster(roster_csv),
        "sessions": [],
    }
    class_dir.mkdir(parents=True, exist_ok=True)
    save_class(cls, class_dir)
    return cls


def load_class(class_dir: str | Path) -> dict:
    path = _class_path(class_dir)
    if not path.exists():
        raise ClassError(f"no class.json in {class_dir} - run 'class init' first")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_class(cls: dict, class_dir: str | Path) -> None:
    with open(_class_path(class_dir), "w", encoding="utf-8") as f:
        json.dump(cls, f, ensure_ascii=False, indent=1)


# ---------------------------------------------------------------- recording a lesson

def _load_class_results(path: str | Path, roster: list[dict]) -> tuple[list[dict], list[str]]:
    """Results CSV for a class: student,q1..qN (group joined from the roster).
    A legacy 'group' column, if present, is ignored in favour of the roster."""
    eal_by_student = {r["student"]: r["eal"] for r in roster}
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        qcols = [c for c in fields if c.lower().startswith("q") and c[1:].isdigit()]
        if "student" not in fields or not qcols:
            raise ClassError("results CSV needs columns: student, q1..qN")
        rows = []
        for i, row in enumerate(reader):
            name = row["student"].strip()
            if name not in eal_by_student:
                raise ClassError(f"results row {i + 2}: {name!r} is not on the roster")
            scores = {}
            for c in qcols:
                v = (row[c] or "").strip()
                if v not in ("0", "1"):
                    raise ClassError(f"results row {i + 2}: {c} must be 0 or 1, got {v!r}")
                scores[c] = int(v)
            rows.append({"student": name,
                         "group": "EAL" if eal_by_student[name] else "non-EAL",
                         "scores": scores})
    if not rows:
        raise ClassError("no result rows")
    absent = sorted(set(eal_by_student) - {r["student"] for r in rows})
    return rows, absent


def _previous_assignments(cls: dict) -> dict[str, str]:
    """Last known tier per student across all recorded sessions."""
    prev: dict[str, str] = {}
    for session in cls["sessions"]:
        for a in session["assignments"]:
            prev[a["student"]] = a["tier"]
    return prev


def load_items(path: str | Path) -> dict[str, str]:
    """Unified assessment model: CSV item,function - one taxonomy for diagnostic,
    exit ticket and every future assessment. No more external manual mapping."""
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or not {"item", "function"} <= set(reader.fieldnames):
            raise ClassError("items CSV needs columns: item, function")
        out = {}
        for i, row in enumerate(reader):
            item, fn = row["item"].strip(), row["function"].strip()
            if fn not in VALID_FUNCTIONS:
                raise ClassError(f"items row {i + 2}: function {fn!r} not in {VALID_FUNCTIONS}")
            if item in out:
                raise ClassError(f"items row {i + 2}: duplicate item {item!r}")
            out[item] = fn
    if not out:
        raise ClassError("items CSV is empty")
    return out


# ---------------------------------------------------------------- skill profile & rationale

def _skill_scores(scores: dict[str, int], functions: dict[str, str]) -> dict[str, float]:
    by_fn: dict[str, list[int]] = {}
    for q, s in scores.items():
        fn = functions.get(q)
        if fn:
            by_fn.setdefault(fn, []).append(s)
    return {fn: round(sum(v) / len(v), 3) for fn, v in sorted(by_fn.items())}


def _band(score: float) -> str:
    if score >= SECURE_AT:
        return "strong"
    if score >= DEVELOPING_AT:
        return "developing"
    return "weak"


def build_profile(scores: dict[str, int], functions: dict[str, str]) -> dict:
    skills = _skill_scores(scores, functions)
    banded = {fn: {"score": s, "band": _band(s)} for fn, s in skills.items()}
    strengths = [fn for fn, v in banded.items() if v["band"] == "strong"]
    below = {fn: s for fn, s in skills.items() if s < SECURE_AT}
    if not below:
        limiting = None                       # everything secure
    elif not strengths:
        limiting = "_foundational"            # nothing secure: foundations, not one gap
    else:
        limiting = min(below, key=below.get)  # weakest skill against a secure base
    return {"skills": banded, "strengths": strengths, "limiting": limiting}


def build_rationale(tier: str, mastery: float, note: str, profile: dict | None,
                    override: dict | None = None) -> str:
    """Answers, in order: why this tier / what is limiting / what next."""
    name = TIER_NAMES[tier].split(" / ")[0]
    if override:
        # The teacher's reason IS the instructional decision here. The machine adds
        # the written-evidence profile for reference and does not prescribe a next
        # move over the teacher's head.
        parts = [f"{name} by teacher override (rule said "
                 f"{TIER_NAMES[override['rule_tier']].split(' / ')[0]}): {override['reason']}."]
        if profile:
            written = ", ".join(f"{fn} {v['score']:.0%}" for fn, v in profile["skills"].items())
            parts.append(f"Written-ticket profile for reference: {written}. "
                         "Teacher's direct evidence takes precedence for tiering.")
        return " ".join(parts)
    parts = [f"{name}: overall readiness {mastery:.0%} ({note})."]
    if profile is None:
        return " ".join(parts)
    if profile["strengths"]:
        parts.append("Secure: " + ", ".join(profile["strengths"]) + ".")
    limiting = profile["limiting"]
    if limiting is None:
        parts.append("No limiting skill this cycle - extend within the tier.")
    elif limiting == "_foundational":
        parts.append("No secure skill yet. Next: " + NEXT_MOVES["_foundational"] + ".")
    else:
        score = profile["skills"][limiting]["score"]
        parts.append(f"Limiting skill: {limiting} ({score:.0%}). "
                     f"Next: {NEXT_MOVES.get(limiting, 'targeted practice on this skill')}.")
        if tier != "t1" and not override:
            parts.append(TIER_PRINCIPLE)
    return " ".join(parts)


def load_overrides(path: str | Path) -> dict[str, dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        need = {"student", "tier", "reason"}
        if not reader.fieldnames or not need <= set(reader.fieldnames):
            raise ClassError("overrides CSV needs columns: student, tier, reason")
        out = {}
        for i, row in enumerate(reader):
            tier = row["tier"].strip()
            if tier not in TIER_ORDER:
                raise ClassError(f"overrides row {i + 2}: unknown tier {tier!r}")
            reason = row["reason"].strip()
            if not reason:
                raise ClassError(f"overrides row {i + 2}: reason is required for an override")
            out[row["student"].strip()] = {"tier": tier, "reason": reason}
    return out


def _gap_by_function(analysis: dict, functions: dict[str, str]) -> dict[str, float | None]:
    """Aggregate per-question gaps into per-function gaps (mean over the
    function's questions), e.g. {'define': 12.5, 'calculate': -4.0}."""
    by_fn: dict[str, list[float]] = {}
    for q, gap in analysis["item_gaps"].items():
        fn = functions.get(q)
        if fn is None or gap is None:
            continue
        by_fn.setdefault(fn, []).append(gap)
    return {fn: round(sum(v) / len(v), 1) for fn, v in sorted(by_fn.items())}


def record_lesson(class_dir: str | Path, results_csv: str | Path,
                  lesson_yaml: str | Path | None = None,
                  items_csv: str | Path | None = None,
                  overrides_csv: str | Path | None = None,
                  topic: str = "") -> dict:
    cls = load_class(class_dir)
    rows, absent = _load_class_results(results_csv, cls["roster"])
    qcols = set(rows[0]["scores"])

    lesson_info: dict = {"topic": topic}
    functions: dict[str, str] = {}
    if lesson_yaml:
        lesson = load_lesson(lesson_yaml)
        functions = {f"q{i + 1}": q["function"] for i, q in enumerate(lesson["exit_ticket"])}
        lesson_info = {"topic": lesson["topic"], "objective": lesson["objective"]}
    if items_csv:  # unified assessment model - overrides lesson-derived mapping
        functions = load_items(items_csv)
    if functions:
        missing = qcols - set(functions)
        if missing:
            raise ClassError(f"function map does not cover items: {', '.join(sorted(missing))}")
        lesson_info["functions"] = {q: functions[q] for q in sorted(qcols, key=lambda c: int(c[1:]))}

    previous = _previous_assignments(cls)
    assignments = assign(rows, previous or None)

    overrides = load_overrides(overrides_csv) if overrides_csv else {}
    unknown = set(overrides) - {a["student"] for a in assignments}
    if unknown:
        raise ClassError(f"override(s) for students not in these results: {', '.join(sorted(unknown))}")
    scores_by_student = {r["student"]: r["scores"] for r in rows}
    for a in assignments:
        ov = overrides.get(a["student"])
        a["override"] = None
        if ov and ov["tier"] != a["tier"]:
            a["override"] = {"rule_tier": a["tier"], "reason": ov["reason"]}
            a["notes"] = f"teacher override: {ov['reason']} (rule said {a['tier']})"
            a["tier"] = ov["tier"]
        # v0.3.3: skill profile + three-question rationale.
        # The profile NEVER changes the tier - tier is overall readiness (or override);
        # the profile shapes what happens inside the tier.
        profile = (build_profile(scores_by_student[a["student"]], functions)
                   if functions else None)
        a["profile"] = profile
        a["rationale"] = build_rationale(a["tier"], a["mastery"], a["notes"],
                                         profile, a["override"])

    analysis = analyze(rows)
    session = {
        "n": len(cls["sessions"]) + 1,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "lesson": lesson_info,
        "absent": absent,
        "assignments": assignments,
        "gap": {
            "gap_pp": analysis["gap_pp"],
            "mastery": {g: analysis["groups"][g]["mastery_rate"] for g in GROUPS},
            "item_gaps": analysis["item_gaps"],
            "by_function": _gap_by_function(analysis, functions),
        },
    }
    cls["sessions"].append(session)
    save_class(cls, class_dir)
    return session


# ---------------------------------------------------------------- trend analysis

def student_timeline(cls: dict, student: str) -> list[dict]:
    if student not in {r["student"] for r in cls["roster"]}:
        raise ClassError(f"{student!r} is not on the roster")
    timeline = []
    for s in cls["sessions"]:
        entry = next((a for a in s["assignments"] if a["student"] == student), None)
        timeline.append({
            "lesson": s["n"],
            "topic": s["lesson"].get("topic", ""),
            "absent": student in s["absent"],
            "mastery": entry["mastery"] if entry else None,
            "tier": entry["tier"] if entry else None,
            "notes": entry["notes"] if entry else ("absent" if student in s["absent"] else ""),
            "override": entry.get("override") if entry else None,
        })
    return timeline


def convergence_verdict(cls: dict) -> dict:
    gaps = [(s["n"], s["gap"]["gap_pp"]) for s in cls["sessions"] if s["gap"]["gap_pp"] is not None]
    if len(gaps) < 2:
        return {"verdict": "insufficient data", "delta_pp": None, "series": gaps,
                "detail": "Need at least two recorded lessons to judge a trend."}
    delta = round(gaps[-1][1] - gaps[0][1], 1)
    if delta <= -CONVERGENCE_BAND_PP:
        verdict = "converging"
        detail = f"Gap narrowed by {abs(delta):.1f} pp from lesson {gaps[0][0]} to {gaps[-1][0]}."
    elif delta >= CONVERGENCE_BAND_PP:
        verdict = "widening"
        detail = (f"Gap widened by {delta:.1f} pp - the current intervention is not "
                  "closing it. Review scaffolds and re-teach before re-tiering.")
    else:
        verdict = "flat"
        detail = f"Gap moved {delta:+.1f} pp - within the +/-{CONVERGENCE_BAND_PP:.0f} pp noise band."
    return {"verdict": verdict, "delta_pp": delta, "series": gaps, "detail": detail}


def function_trend(cls: dict) -> dict[str, list[tuple[int, float]]]:
    """Per question-function gap across lessons: {'calculate': [(1, 20.8), (2, 12.5)], ...}"""
    out: dict[str, list[tuple[int, float]]] = {}
    for s in cls["sessions"]:
        for fn, gap in s["gap"].get("by_function", {}).items():
            out.setdefault(fn, []).append((s["n"], gap))
    return out
