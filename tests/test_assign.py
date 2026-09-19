from pathlib import Path

import pytest

from tierbridge.assign import (
    assign, load_previous, render_grouping_sheet, write_assignments_csv,
)
from tierbridge.gap import load_results

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def _row(student, group, *scores):
    return {"student": student, "group": group,
            "scores": {f"q{i+1}": s for i, s in enumerate(scores)}}


# ---------- base tiering: readiness only ----------

def test_tier_from_mastery_thresholds():
    rows = [_row("A", "non-EAL", 1, 1, 1),   # 1.0  -> t3
            _row("B", "non-EAL", 1, 1, 0),   # 0.67 -> t2
            _row("C", "non-EAL", 1, 0, 0)]   # 0.33 -> t1
    tiers = {a["student"]: a["tier"] for a in assign(rows)}
    assert tiers == {"A": "t3", "B": "t2", "C": "t1"}


def test_eal_never_lowers_tier_but_keeps_language_support():
    rows = [_row("E", "EAL", 1, 1, 1), _row("N", "non-EAL", 1, 1, 1)]
    a = {x["student"]: x for x in assign(rows)}
    assert a["E"]["tier"] == a["N"]["tier"] == "t3"
    assert a["E"]["language_support"] is True
    assert a["N"]["language_support"] is False


# ---------- movement rules ----------

def test_one_step_limit_up():
    # was t1, scored 0.67 -> base t2 (one step, allowed)
    rows = [_row("S", "EAL", 1, 1, 0)]
    a = assign(rows, {"S": "t1"})[0]
    assert a["tier"] == "t2"
    assert "moves up" in a["notes"]


def test_one_step_limit_blocks_double_jump_down():
    # was t3, bombs the ticket (0.0 -> base t1) but only drops one step
    rows = [_row("S", "non-EAL", 0, 0, 0)]
    a = assign(rows, {"S": "t3"})[0]
    assert a["tier"] == "t2"
    assert "limited to one step" in a["notes"]
    assert "re-teach" in a["notes"]


def test_anti_crutch_rule_forces_move_up():
    # was t1 and mastered with full scaffolds -> must move to t2
    rows = [_row("S", "EAL", 1, 1, 1)]
    a = assign(rows, {"S": "t1"})[0]
    assert a["tier"] == "t2"
    assert "anti-crutch" in a["notes"]


def test_stay_note():
    rows = [_row("S", "non-EAL", 1, 1, 0)]
    a = assign(rows, {"S": "t2"})[0]
    assert a["tier"] == "t2"
    assert a["notes"] == "stays"


def test_first_assignment_note_without_previous():
    a = assign([_row("S", "EAL", 1, 0, 0)])[0]
    assert a["notes"] == "first assignment"


# ---------- io ----------

def test_load_previous_validates(tmp_path):
    p = tmp_path / "prev.csv"
    p.write_text("student,tier\nS1,t2\n", encoding="utf-8")
    assert load_previous(p) == {"S1": "t2"}
    p.write_text("student,tier\nS1,gold\n", encoding="utf-8")
    with pytest.raises(ValueError, match="gold"):
        load_previous(p)


def test_assignments_csv_roundtrip(tmp_path):
    rows = load_results(EXAMPLES / "results_demo.csv")
    assignments = assign(rows)
    out = tmp_path / "a.csv"
    write_assignments_csv(assignments, out)
    text = out.read_text(encoding="utf-8")
    assert "student,group,mastery,tier,language_support,notes" in text
    assert text.count("\n") == len(assignments) + 1


def test_grouping_sheet_renders_rules_and_eal_marker():
    rows = load_results(EXAMPLES / "results_demo.csv")
    html = render_grouping_sheet(assign(rows))
    assert "anti-crutch" in html
    assert "never from EAL status" in html
    assert " *" in html          # at least one EAL marker
    assert "Stretch / Extension" in html


# ---------- CLI ----------

def test_cli_assign(tmp_path):
    from tierbridge.__main__ import main
    rc = main(["assign", str(EXAMPLES / "results_demo.csv"), "-o", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / "results_demo_assignments.csv").exists()
    assert (tmp_path / "results_demo_groups.html").exists()


def test_cli_assign_with_previous(tmp_path):
    from tierbridge.__main__ import main
    prev = tmp_path / "prev.csv"
    prev.write_text("student,tier\nS01,t1\n", encoding="utf-8")
    rc = main(["assign", str(EXAMPLES / "results_demo.csv"),
               "-o", str(tmp_path), "--previous", str(prev)])
    assert rc == 0
    text = (tmp_path / "results_demo_assignments.csv").read_text(encoding="utf-8")
    assert "S01" in text
