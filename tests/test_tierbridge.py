import copy
import json
from pathlib import Path

import pytest

from tierbridge.gap import ResultsError, analyze, load_results, render_gap_report
from tierbridge.generate import build_pack, enrich_with_ai, validate_enriched
from tierbridge.models import LessonError, load_lesson, load_scaffolds, validate_lesson
from tierbridge.render import render_pack

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
LESSON = load_lesson(EXAMPLES / "ped_lesson.yaml")


# ---------- models / validation ----------

def test_example_lesson_valid():
    validate_lesson(LESSON)  # should not raise


def test_missing_field_rejected():
    bad = copy.deepcopy(LESSON)
    del bad["objective"]
    with pytest.raises(LessonError, match="objective"):
        validate_lesson(bad)


def test_bad_exit_ticket_function_rejected():
    bad = copy.deepcopy(LESSON)
    bad["exit_ticket"][0]["function"] = "meditate"
    with pytest.raises(LessonError, match="meditate"):
        validate_lesson(bad)


def test_empty_tier_tasks_rejected():
    bad = copy.deepcopy(LESSON)
    bad["worksheets"]["t2"]["tasks"] = []
    with pytest.raises(LessonError, match="t2"):
        validate_lesson(bad)


def test_scaffold_library_shape():
    lib = load_scaffolds()
    assert set(lib["tiers"]) == {"t1", "t2", "t3"}
    assert "calculate" in lib["sentence_frames"]
    assert "fading" in lib["teacher_moves"]


# ---------- pack building: the core invariant ----------

def test_same_objective_and_criteria_across_tiers():
    pack = build_pack(LESSON)
    assert pack["mode"] == "authored"
    # exit ticket questions identical for every tier; only frames differ
    for q in pack["exit_ticket"]:
        assert q["frames"]["t3"] == []          # no support at extension tier
    assert pack["exit_ticket"][1]["frames"]["t1"]  # calculate → t1 has step frames


def test_glossary_policy_by_tier():
    pack = build_pack(LESSON)
    assert pack["tiers"]["t1"]["glossary_bilingual"] is True
    assert pack["tiers"]["t2"]["glossary"] is True
    assert pack["tiers"]["t2"]["glossary_bilingual"] is False
    assert pack["tiers"]["t3"]["glossary"] is False


def test_template_mode_builds_shells():
    lesson = copy.deepcopy(LESSON)
    del lesson["worksheets"]
    pack = build_pack(lesson)
    assert pack["mode"] == "template"
    t1_tasks = pack["tiers"]["t1"]["tasks"]
    assert len(t1_tasks) == len(lesson["success_criteria"])
    assert all(t["template_shell"] for t in t1_tasks)
    # extension tier gets an extra challenge shell
    assert any("Challenge" in t["title"] for t in pack["tiers"]["t3"]["tasks"])


# ---------- rendering ----------

def test_render_contains_all_sheets_and_bilingual_glossary():
    html = render_pack(build_pack(LESSON))
    assert html.count("class=\"sheet") == 7  # notes + 3 worksheets + 3 exit tickets
    assert "需求价格弹性" in html            # zh only on t1 sheet
    assert html.count("需求价格弹性") == 1
    assert "Same questions for every tier" in html
    assert "Scaffold fading" in html


def test_render_objective_identical_on_every_worksheet():
    html = render_pack(build_pack(LESSON))
    assert html.count("Learning objective (same for the whole class)") == 3


def test_ai_drafted_flag_renders_review_warning():
    lesson = copy.deepcopy(LESSON)
    lesson["ai_drafted"] = True
    html = render_pack(build_pack(lesson))
    assert "review before class" in html.lower()


# ---------- AI enrichment contract ----------

def _fake_ai_payload():
    task = {"title": "Task", "instructions": "Do the thing with the numbers.", "frames": []}
    return {
        "t1": {"tasks": [dict(task), dict(task)]},
        "t2": {"tasks": [dict(task), dict(task)]},
        "t3": {"tasks": [dict(task), {"title": "Challenge: transfer",
                                      "instructions": "Apply to canteen.", "frames": []}]},
    }


def test_validate_enriched_accepts_good_payload():
    assert validate_enriched(_fake_ai_payload()) == []


def test_validate_enriched_requires_challenge_in_t3():
    p = _fake_ai_payload()
    p["t3"]["tasks"] = [{"title": "Task", "instructions": "x", "frames": []},
                        {"title": "Task2", "instructions": "y", "frames": []}]
    assert any("challenge" in x for x in validate_enriched(p))


def test_validate_enriched_rejects_overlong_instructions():
    p = _fake_ai_payload()
    p["t1"]["tasks"][0]["instructions"] = "word " * 80
    assert any("over 70 words" in x for x in validate_enriched(p))


def test_enrich_with_ai_roundtrip_mock():
    def fake_chat(messages, temperature=0.4):
        return json.dumps(_fake_ai_payload())

    lesson = copy.deepcopy(LESSON)
    del lesson["worksheets"]
    enriched = enrich_with_ai(lesson, fake_chat)
    assert enriched["ai_drafted"] is True
    pack = build_pack(enriched)
    assert pack["mode"] == "authored"


def test_enrich_with_ai_rejects_bad_payload():
    def fake_chat(messages, temperature=0.4):
        return json.dumps({"t1": {"tasks": []}})

    with pytest.raises(ValueError, match="rejected"):
        enrich_with_ai(copy.deepcopy(LESSON), fake_chat)


# ---------- gap analysis ----------

def test_gap_analysis_demo_csv():
    rows = load_results(EXAMPLES / "results_demo.csv")
    a = analyze(rows)
    assert a["n"] == 14
    assert a["groups"]["EAL"]["n"] == 6
    assert a["groups"]["non-EAL"]["n"] == 8
    # hand-checked: EAL mastered (>=2/3): S01,S03,S05,S06 = 4/6; non-EAL: 7/8
    assert a["groups"]["EAL"]["mastery_rate"] == pytest.approx(4 / 6)
    assert a["groups"]["non-EAL"]["mastery_rate"] == pytest.approx(7 / 8)
    assert a["gap_pp"] == pytest.approx(20.8, abs=0.1)


def test_gap_per_item_direction():
    a = analyze(load_results(EXAMPLES / "results_demo.csv"))
    assert a["item_gaps"]["q3"] > 0  # interpretation question shows the biggest EAL gap


def test_gap_bad_group_rejected():
    import io
    import tierbridge.gap as gap_mod
    bad = "student,group,q1\nS1,ESL,1\n"
    path = EXAMPLES.parent / "out" / "_bad.csv"
    path.parent.mkdir(exist_ok=True)
    path.write_text(bad, encoding="utf-8")
    with pytest.raises(ResultsError, match="group"):
        load_results(path)


def test_gap_bad_score_rejected(tmp_path):
    p = tmp_path / "r.csv"
    p.write_text("student,group,q1\nS1,EAL,2\n", encoding="utf-8")
    with pytest.raises(ResultsError, match="q1"):
        load_results(p)


def test_gap_report_renders():
    a = analyze(load_results(EXAMPLES / "results_demo.csv"))
    html = render_gap_report(a)
    assert "Mastery gap" in html and "pp" in html
    assert "<svg" in html
    assert "fade the scaffolds" in html


# ---------- CLI ----------

def test_cli_generate_and_gap(tmp_path):
    from tierbridge.__main__ import main
    rc = main(["generate", str(EXAMPLES / "ped_lesson.yaml"), "-o", str(tmp_path)])
    assert rc == 0
    out = tmp_path / "ped_lesson_pack.html"
    assert out.exists() and "TierBridge" in out.read_text(encoding="utf-8")

    rc = main(["gap", str(EXAMPLES / "results_demo.csv"), "-o", str(tmp_path)])
    assert rc == 0
    assert (tmp_path / "results_demo_gap.html").exists()
