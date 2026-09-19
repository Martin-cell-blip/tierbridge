from pathlib import Path

import pytest

from tierbridge.classroom import (
    ClassError, convergence_verdict, function_trend, init_class, load_class,
    load_overrides, load_roster, record_lesson, student_timeline,
)
from tierbridge.trend import render_trend

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
DEMO = EXAMPLES / "class_demo"
LESSON_YAML = EXAMPLES / "ped_lesson.yaml"


@pytest.fixture()
def demo_class(tmp_path):
    """Class with all three demo lessons recorded (override on lesson 2)."""
    cdir = tmp_path / "10B"
    init_class("10B Economics", DEMO / "roster.csv", cdir)
    record_lesson(cdir, DEMO / "lesson1.csv", lesson_yaml=LESSON_YAML)
    record_lesson(cdir, DEMO / "lesson2.csv", lesson_yaml=LESSON_YAML,
                  overrides_csv=DEMO / "overrides2.csv")
    record_lesson(cdir, DEMO / "lesson3.csv", lesson_yaml=LESSON_YAML)
    return cdir


# ---------- roster / init ----------

def test_roster_loads():
    roster = load_roster(DEMO / "roster.csv")
    assert len(roster) == 10
    assert sum(r["eal"] for r in roster) == 4


def test_roster_duplicate_rejected(tmp_path):
    p = tmp_path / "r.csv"
    p.write_text("student,eal\nA,1\nA,0\n", encoding="utf-8")
    with pytest.raises(ClassError, match="duplicate"):
        load_roster(p)


def test_roster_bad_eal_rejected(tmp_path):
    p = tmp_path / "r.csv"
    p.write_text("student,eal\nA,maybe\n", encoding="utf-8")
    with pytest.raises(ClassError, match="eal"):
        load_roster(p)


def test_init_refuses_to_overwrite(tmp_path):
    cdir = tmp_path / "c"
    init_class("X", DEMO / "roster.csv", cdir)
    with pytest.raises(ClassError, match="already exists"):
        init_class("X", DEMO / "roster.csv", cdir)


# ---------- recording ----------

def test_record_joins_group_from_roster(tmp_path):
    cdir = tmp_path / "c"
    init_class("X", DEMO / "roster.csv", cdir)
    session = record_lesson(cdir, DEMO / "lesson1.csv", lesson_yaml=LESSON_YAML)
    alex = next(a for a in session["assignments"] if a["student"] == "Alex")
    assert alex["group"] == "EAL" and alex["language_support"] is True
    assert session["gap"]["gap_pp"] == pytest.approx(50.0)
    assert session["gap"]["by_function"]  # ped lesson gives define/calculate/interpret


def test_record_rejects_student_not_on_roster(tmp_path):
    cdir = tmp_path / "c"
    init_class("X", DEMO / "roster.csv", cdir)
    bad = tmp_path / "bad.csv"
    bad.write_text("student,q1\nZoe,1\n", encoding="utf-8")
    with pytest.raises(ClassError, match="Zoe"):
        record_lesson(cdir, bad)


def test_absent_students_tracked(demo_class):
    cls = load_class(demo_class)
    assert cls["sessions"][1]["absent"] == ["Hana"]      # missing from lesson2.csv
    assert cls["sessions"][2]["absent"] == []


def test_auto_previous_across_sessions(demo_class):
    cls = load_class(demo_class)
    alex = student_timeline(cls, "Alex")
    # Alex (EAL): 33% t1 -> 67% moves up to t2 -> 100% moves up to t3
    assert [t["tier"] for t in alex] == ["t1", "t2", "t3"]
    assert "moves up" in alex[1]["notes"]


def test_override_applied_and_recorded(demo_class):
    cls = load_class(demo_class)
    ming_l2 = next(a for a in cls["sessions"][1]["assignments"] if a["student"] == "Ming")
    assert ming_l2["tier"] == "t2"
    assert ming_l2["override"]["rule_tier"] == "t1"
    assert "language only" in ming_l2["override"]["reason"]
    # lesson 3 uses the OVERRIDDEN tier as previous
    ming_l3 = next(a for a in cls["sessions"][2]["assignments"] if a["student"] == "Ming")
    assert ming_l3["tier"] == "t2"
    assert ming_l3["notes"] == "stays"


def test_override_requires_reason(tmp_path):
    p = tmp_path / "ov.csv"
    p.write_text("student,tier,reason\nMing,t2,\n", encoding="utf-8")
    with pytest.raises(ClassError, match="reason"):
        load_overrides(p)


def test_override_unknown_student_rejected(tmp_path):
    cdir = tmp_path / "c"
    init_class("X", DEMO / "roster.csv", cdir)
    ov = tmp_path / "ov.csv"
    ov.write_text("student,tier,reason\nZoe,t2,new arrival\n", encoding="utf-8")
    with pytest.raises(ClassError, match="Zoe"):
        record_lesson(cdir, DEMO / "lesson1.csv", overrides_csv=ov)


# ---------- trend analysis ----------

def test_gap_series_converging(demo_class):
    cls = load_class(demo_class)
    v = convergence_verdict(cls)
    assert v["verdict"] == "converging"
    assert [g for _, g in v["series"]] == [pytest.approx(50.0), pytest.approx(25.0),
                                           pytest.approx(0.0)]
    assert v["delta_pp"] == pytest.approx(-50.0)


def test_convergence_insufficient_with_one_lesson(tmp_path):
    cdir = tmp_path / "c"
    init_class("X", DEMO / "roster.csv", cdir)
    record_lesson(cdir, DEMO / "lesson1.csv")
    assert convergence_verdict(load_class(cdir))["verdict"] == "insufficient data"


def test_function_trend_interpret_gap_shrinks(demo_class):
    trend = function_trend(load_class(demo_class))
    interpret = dict(trend["interpret"])
    assert interpret[1] > interpret[3]      # biggest EAL gap narrows over the term
    assert set(trend) == {"define", "calculate", "interpret"}


def test_student_timeline_absent_marked(demo_class):
    tl = student_timeline(load_class(demo_class), "Hana")
    assert tl[1]["absent"] is True and tl[1]["tier"] is None
    assert tl[2]["tier"] is not None


def test_timeline_unknown_student(demo_class):
    with pytest.raises(ClassError, match="Zoe"):
        student_timeline(load_class(demo_class), "Zoe")


# ---------- trend report ----------

def test_trend_report_renders(demo_class):
    html = render_trend(load_class(demo_class))
    assert "Gap convergence: converging" in html
    assert "teacher override" in html       # Ming's rationale visible
    assert "†" in html                      # override marker
    assert "Alex *" in html                 # EAL marker
    assert "absent" in html
    assert html.count("<th>L") == 3 or "L3" in html


# ---------- CLI ----------

def test_cli_class_workflow(tmp_path):
    from tierbridge.__main__ import main
    cdir = tmp_path / "10B"
    assert main(["class", "init", "10B Economics",
                 "--roster", str(DEMO / "roster.csv"), "--dir", str(cdir)]) == 0
    assert main(["class", "record", str(cdir), str(DEMO / "lesson1.csv"),
                 "--lesson", str(LESSON_YAML)]) == 0
    assert main(["class", "record", str(cdir), str(DEMO / "lesson2.csv"),
                 "--lesson", str(LESSON_YAML),
                 "--overrides", str(DEMO / "overrides2.csv")]) == 0
    assert main(["class", "trend", str(cdir), "-o", str(tmp_path)]) == 0
    assert (tmp_path / "10B_trend.html").exists()
