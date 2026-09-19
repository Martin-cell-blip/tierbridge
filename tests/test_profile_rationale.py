from pathlib import Path

import pytest

from tierbridge.classroom import (
    ClassError, TIER_PRINCIPLE, build_profile, build_rationale, init_class,
    load_class, load_items, record_lesson,
)

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
TC02 = EXAMPLES / "tc02_ib12"


# ---------------------------------------------------------------- items model

def test_load_items(tmp_path):
    p = tmp_path / "items.csv"
    p.write_text("item,function\nq1,concept\nq2,calculate\nq3,interpret\n", encoding="utf-8")
    assert load_items(p) == {"q1": "concept", "q2": "calculate", "q3": "interpret"}


def test_load_items_rejects_unknown_function(tmp_path):
    p = tmp_path / "items.csv"
    p.write_text("item,function\nq1,vibes\n", encoding="utf-8")
    with pytest.raises(ClassError, match="vibes"):
        load_items(p)


def test_record_rejects_uncovered_items(tmp_path):
    cdir = tmp_path / "c"
    init_class("X", TC02 / "roster.csv", cdir)
    items = tmp_path / "items.csv"
    items.write_text("item,function\nq1,concept\n", encoding="utf-8")  # results have q1..q10
    with pytest.raises(ClassError, match="does not cover"):
        record_lesson(cdir, TC02 / "diagnostic.csv", items_csv=items)


# ---------------------------------------------------------------- profile

def _profile(scores, functions):
    return build_profile(scores, functions)


FUNCS3 = {"q1": "concept", "q2": "concept", "q3": "calculate", "q4": "calculate", "q5": "interpret"}


def test_profile_limiting_skill_named():
    # Michael-style: concept and calculate secure, interpret failing
    p = _profile({"q1": 1, "q2": 1, "q3": 1, "q4": 1, "q5": 0}, FUNCS3)
    assert p["strengths"] == ["calculate", "concept"]
    assert p["limiting"] == "interpret"
    assert p["skills"]["interpret"]["band"] == "weak"


def test_profile_all_secure_no_limiting():
    p = _profile({"q1": 1, "q2": 1, "q3": 1, "q4": 1, "q5": 1}, FUNCS3)
    assert p["limiting"] is None


def test_profile_nothing_secure_is_foundational_not_one_gap():
    # George-style: no secure base - the story is foundations, not a single gap
    p = _profile({"q1": 0, "q2": 0, "q3": 1, "q4": 0, "q5": 0}, FUNCS3)
    assert p["strengths"] == []
    assert p["limiting"] == "_foundational"


# ---------------------------------------------------------------- rationale

def test_rationale_answers_three_questions_michael():
    p = _profile({"q1": 1, "q2": 1, "q3": 1, "q4": 1, "q5": 0}, FUNCS3)
    r = build_rationale("t3", 0.8, "stays", p)
    assert "Stretch" in r and "80%" in r            # why this tier
    assert "Limiting skill: interpret" in r          # what is limiting
    assert "interpretation task" in r                # what next
    assert TIER_PRINCIPLE in r                       # weakness shapes tasks, not tier


def test_rationale_all_secure_extends():
    p = _profile({"q1": 1, "q2": 1, "q3": 1, "q4": 1, "q5": 1}, FUNCS3)
    r = build_rationale("t3", 1.0, "stays", p)
    assert "No limiting skill" in r and "extend" in r


def test_rationale_foundational():
    p = _profile({"q1": 0, "q2": 0, "q3": 1, "q4": 0, "q5": 0}, FUNCS3)
    r = build_rationale("t1", 0.2, "stays", p)
    assert "foundations first" in r


def test_rationale_override_carries_reason_and_profile():
    p = _profile({"q1": 1, "q2": 0, "q3": 1, "q4": 0, "q5": 0}, FUNCS3)
    ov = {"rule_tier": "t1", "reason": "concept secure orally; language-limited"}
    r = build_rationale("t2", 0.4, "teacher override: ...", p, override=ov)
    assert "teacher override" in r.lower()
    assert "rule said Bridge" in r
    assert "language-limited" in r
    # machine defers: no prescription over the teacher's head, profile is reference-only
    assert "Next:" not in r
    assert "Written-ticket profile" in r
    assert "precedence" in r


# ---------------------------------------------------------------- end to end: weakness never demotes

@pytest.fixture()
def ib12(tmp_path):
    cdir = tmp_path / "ib12"
    init_class("IB Economics HL Y12", TC02 / "roster.csv", cdir)
    record_lesson(cdir, TC02 / "diagnostic.csv", items_csv=TC02 / "items_diagnostic.csv",
                  topic="Diagnostic")
    record_lesson(cdir, TC02 / "exit_ticket.csv", items_csv=TC02 / "items_exit.csv",
                  overrides_csv=TC02 / "overrides.csv", topic="Indirect Tax")
    return load_class(cdir)


def _get(cls, n, student):
    return next(a for a in cls["sessions"][n]["assignments"] if a["student"] == student)


def test_michael_keeps_tier_with_named_weakness(ib12):
    m = _get(ib12, 1, "Michael")
    assert m["tier"] == "t3"                          # weakness never demotes
    assert m["profile"]["limiting"] == "interpret"
    assert "Limiting skill: interpret" in m["rationale"]
    assert TIER_PRINCIPLE in m["rationale"]


def test_julia_no_limiting_language_support_kept(ib12):
    j = _get(ib12, 1, "Julia")
    assert j["tier"] == "t3" and j["language_support"] is True
    assert j["profile"]["limiting"] is None


def test_george_foundational_rationale(ib12):
    g = _get(ib12, 1, "George")
    assert g["tier"] == "t1" and g["language_support"] is False
    assert "foundations first" in g["rationale"]


def test_alex_moves_up_with_interpret_gap_named(ib12):
    a = _get(ib12, 1, "Alex")
    assert a["tier"] == "t3" and "moves up" in a["notes"]
    assert a["profile"]["limiting"] == "interpret"


def test_lina_override_rationale_and_previous(ib12):
    l = _get(ib12, 1, "Lina")
    assert l["tier"] == "t2" and l["override"]["rule_tier"] == "t1"
    assert "override" in l["rationale"].lower()
    from tierbridge.classroom import _previous_assignments
    assert _previous_assignments(ib12)["Lina"] == "t2"


def test_diagnostic_by_function_now_automatic(ib12):
    by_fn = ib12["sessions"][0]["gap"]["by_function"]
    assert set(by_fn) == {"concept", "calculate", "interpret"}
