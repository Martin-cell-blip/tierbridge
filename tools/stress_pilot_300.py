# -*- coding: utf-8 -*-
"""300-student full-pipeline stress run over the pilot_300 fixture.

Test tooling only - no product code is modified. Converts the fixture into the
REAL input schemas, then drives the REAL CLIs / APIs:

  TierBridge: class init -> 6x class record (items map, per-lesson overrides,
              absences as missing rows) -> class trend, run twice for determinism.
  edulab:     fixture cohorts -> cluster enrollment, pre/post learning scores,
              engagement-metric rejection demo, report.
  EconLens:   the 10 fixture cases through the offline deterministic pipeline.

Run from the tierbridge project root:  python tools/stress_pilot_300.py
"""
from __future__ import annotations

import csv
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

TB = Path(__file__).resolve().parents[1]
ROOT = TB / "testdata" / "pilot_300"
CONV = ROOT / "converted"
DEV = TB.parent

sys.path.insert(0, str(TB))
sys.path.insert(0, str(DEV / "edulab"))
sys.path.insert(0, str(DEV / "econlens"))

FUNCTION_ITEMS = {  # fixture taxonomy: 5 items per function, q1..q15
    "concept": [f"q{i}" for i in range(1, 6)],
    "calculate": [f"q{i}" for i in range(6, 11)],
    "interpret": [f"q{i}" for i in range(11, 16)],
}
ALL_ITEMS = [f"q{i}" for i in range(1, 16)]

report: list[str] = []


def log(msg: str) -> None:
    print(msg)
    report.append(msg)


def check(name: str, ok: bool, detail: str = "") -> None:
    log(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""))
    if not ok:
        raise SystemExit(f"verification failed: {name}")


# ------------------------------------------------------------ conversion

def convert() -> None:
    if CONV.exists():
        shutil.rmtree(CONV)
    CONV.mkdir(parents=True)

    # roster: student_id/name/... -> student,eal
    with (ROOT / "roster.csv").open(encoding="utf-8") as f:
        roster = list(csv.DictReader(f))
    with (CONV / "roster.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["student", "eal"])
        w.writeheader()
        for r in roster:
            w.writerow({"student": r["student_id"], "eal": r["eal"]})

    # items map is already in product schema
    shutil.copy(ROOT / "items.csv", CONV / "items.csv")

    # lessons: aggregate per-function scores -> binary q1..q15 (k = round(score*5)
    # ones per function). Absent students are OMITTED (the product's absent path).
    for n in range(1, 7):
        with (ROOT / "lessons" / f"lesson_{n:02d}.csv").open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        with (CONV / f"lesson_{n:02d}.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["student"] + ALL_ITEMS)
            w.writeheader()
            for r in rows:
                if r["absent"] == "true":
                    continue
                out = {"student": r["student_id"]}
                for fn, items in FUNCTION_ITEMS.items():
                    k = round(float(r[fn]) * len(items))
                    for j, item in enumerate(items):
                        out[item] = 1 if j < k else 0
                w.writerow(out)

    # overrides: lesson,from,to,reason -> per-lesson student,tier,reason files
    with (ROOT / "overrides.csv").open(encoding="utf-8") as f:
        for ov in csv.DictReader(f):
            path = CONV / f"overrides_lesson_{int(ov['lesson']):02d}.csv"
            new = not path.exists()
            with path.open("a", newline="", encoding="utf-8") as f2:
                w = csv.DictWriter(f2, fieldnames=["student", "tier", "reason"])
                if new:
                    w.writeheader()
                w.writerow({"student": ov["student_id"], "tier": ov["to_tier"],
                            "reason": ov["reason"]})
    log(f"conversion done -> {CONV}")


# ------------------------------------------------------------ tierbridge pipeline

def cli(*args: str) -> float:
    t0 = time.perf_counter()
    res = subprocess.run([sys.executable, "-m", "tierbridge", *args],
                         cwd=TB, capture_output=True, text=True)
    dt = time.perf_counter() - t0
    if res.returncode != 0:
        raise SystemExit(f"CLI failed: {args}\n{res.stdout}\n{res.stderr}")
    return dt


def run_pipeline(run_dir: Path) -> dict[str, float]:
    if run_dir.exists():
        shutil.rmtree(run_dir)
    times = {}
    times["init"] = cli("class", "init", "Pilot300 Stress", "--roster",
                        str(CONV / "roster.csv"), "--dir", str(run_dir))
    for n in range(1, 7):
        args = ["class", "record", str(run_dir), str(CONV / f"lesson_{n:02d}.csv"),
                "--items", str(CONV / "items.csv"), "--topic", f"Lesson {n}"]
        ov = CONV / f"overrides_lesson_{n:02d}.csv"
        if ov.exists():
            args += ["--overrides", str(ov)]
        times[f"record_{n}"] = cli(*args)
    times["trend"] = cli("class", "trend", str(run_dir), "-o", str(run_dir.parent))
    return times


def strip_volatile(obj):
    if isinstance(obj, dict):
        return {k: strip_volatile(v) for k, v in obj.items()
                if k not in ("recorded_at", "created_at")}
    if isinstance(obj, list):
        return [strip_volatile(x) for x in obj]
    return obj


def verify_tierbridge() -> None:
    cls = json.loads((CONV / "run_a" / "class.json").read_text(encoding="utf-8"))
    sessions = cls["sessions"]

    check("roster 300/300", len(cls["roster"]) == 300, f"{len(cls['roster'])} students")
    check("6 lessons recorded", len(sessions) == 6)

    total_absent = sum(len(s["absent"]) for s in sessions)
    check("27 absences handled as absent", total_absent == 27, f"{total_absent} absent records")
    for s in sessions:
        present = {a["student"] for a in s["assignments"]}
        check(f"L{s['n']}: absent students carry no score",
              not (present & set(s["absent"])))
        check(f"L{s['n']}: 300 unique students accounted for",
              len(present) + len(s["absent"]) == 300 and len(present) == len(s["assignments"]))
        bad_tiers = [a["tier"] for a in s["assignments"] if a["tier"] not in ("t1", "t2", "t3")]
        check(f"L{s['n']}: no illegal tiers", not bad_tiers)
        check(f"L{s['n']}: by_function has 3 functions",
              set(s["gap"]["by_function"]) == {"concept", "calculate", "interpret"})

    # overrides: applied with reason, or rule already agreed (no-op)
    with (ROOT / "overrides.csv").open(encoding="utf-8") as f:
        fixture_ovs = list(csv.DictReader(f))
    applied = 0
    for ov in fixture_ovs:
        lesson, sid, to_tier = int(ov["lesson"]), ov["student_id"], ov["to_tier"]
        a = next(x for x in sessions[lesson - 1]["assignments"] if x["student"] == sid)
        check(f"override L{lesson} {sid}: final tier == {to_tier}", a["tier"] == to_tier)
        if a["override"]:
            applied += 1
            check(f"override L{lesson} {sid}: reason recorded",
                  bool(a["override"]["reason"].strip()))
        else:
            log(f"  [NOTE] override L{lesson} {sid}: rule already assigned {to_tier} "
                "(override was a no-op; nothing to record)")
        # override tier becomes previous for the NEXT lesson
        nxt = next(x for x in sessions[lesson]["assignments"] if x["student"] == sid)
        step = abs("t1 t2 t3".split().index(nxt["tier"]) - "t1 t2 t3".split().index(to_tier))
        check(f"override L{lesson} {sid}: next lesson moves <=1 step from {to_tier}",
              step <= 1, f"next tier {nxt['tier']}")
    log(f"  overrides applied={applied}/3 (rest were rule-agreed no-ops)")

    # trend report consistent with class.json
    html = (CONV / "run_a_trend.html").read_text(encoding="utf-8")
    for s in sessions:
        g = s["gap"]["gap_pp"]
        if g is not None:
            check(f"trend shows L{s['n']} gap {g:+.1f} pp", f"{g:+.1f} pp" in html)
    check("trend has all 300 students", html.count("<tr><td class='name'>") == 300)

    # determinism
    a = strip_volatile(json.loads((CONV / "run_a" / "class.json").read_text(encoding="utf-8")))
    b = strip_volatile(json.loads((CONV / "run_b" / "class.json").read_text(encoding="utf-8")))
    check("same seed rerun -> identical class.json (timestamps excluded)", a == b)

    log("  gap_pp series: " + ", ".join(f"L{s['n']}={s['gap']['gap_pp']:+.1f}" for s in sessions))


# ------------------------------------------------------------ edulab

def run_edulab() -> None:
    from edulab.experiment import (enroll_clusters, init_experiment,
                                   record_measure, record_metrics)
    from edulab.metrics import MetricTypeError
    from edulab.report import analyze, render_report
    from edulab.experiment import load as load_exp

    exp_dir = CONV / "edulab_exp"
    if exp_dir.exists():
        shutil.rmtree(exp_dir)
    t0 = time.perf_counter()

    with (ROOT / "edulab" / "cohorts.csv").open(encoding="utf-8") as f:
        cohorts = list(csv.DictReader(f))
    control = sorted(c["student_id"] for c in cohorts if c["cohort"] == "control")
    treatment = sorted(c["student_id"] for c in cohorts if c["cohort"] == "treatment")

    init_experiment(exp_dir, "Pilot300 edulab stress", "control cohort",
                    "treatment cohort", seed=20260825)
    enroll_clusters(exp_dir, control, treatment, label="fixture cohort split")

    for which in ("pre", "post"):
        src = ROOT / "edulab" / f"{which}.csv"
        dst = CONV / f"edulab_{which}.csv"
        with src.open(encoding="utf-8") as f, dst.open("w", newline="", encoding="utf-8") as g:
            w = csv.DictWriter(g, fieldnames=["participant", "score"])
            w.writeheader()
            for r in csv.DictReader(f):
                w.writerow({"participant": r["student_id"], "score": r["learning_score"]})
        record_measure(exp_dir, which, dst)

    # the fixture's product_engagement is not a registered metric - the registry
    # must reject it rather than let it blend into results
    probe = CONV / "edulab_engagement_probe.csv"
    probe.write_text("participant,metric,value\nS001,product_engagement,55\n", encoding="utf-8")
    try:
        record_metrics(exp_dir, "product", probe)
        check("registry rejects unregistered 'product_engagement'", False)
    except MetricTypeError:
        check("registry rejects unregistered 'product_engagement'", True)

    exp = load_exp(exp_dir)
    a = analyze(exp)
    (CONV / "edulab_report.html").write_text(render_report(exp), encoding="utf-8")
    dt = time.perf_counter() - t0
    g = a["learning"]["groups"]
    log(f"edulab: n control={a['n']['control']} treatment={a['n']['treatment']} | "
        f"paired {g['control']['n_paired']}/{g['treatment']['n_paired']} | "
        f"normalized gain C={g['control']['normalized']} T={g['treatment']['normalized']} | "
        f"diff={a['learning']['gain_diff']} | verdict={a['verdict']} | {dt:.2f}s")
    check("edulab enrollment marked quasi-experimental (clusters, honestly labeled)",
          "quasi-experimental" in exp["assignment_method"])
    check("edulab verdict computed", a["verdict"] in
          ("learning-win", "learning-flat", "learning-loss"))


# ------------------------------------------------------------ econlens

def run_econlens() -> None:
    from econlens.workspace import check_focus_question
    from econlens.preflight import run_preflight
    from econlens.coach import run_coach

    t0 = time.perf_counter()
    ec = ROOT / "econlens"
    rq_cases = json.loads((ec / "rq_cases.json").read_text(encoding="utf-8"))
    for case in rq_cases:
        res = check_focus_question(case["text"])
        log(f"econlens RQ {case['id']}: status={res['status']} (expected {case['expected']})")

    for fname, stage in (("claim_cases.json", "claim"),
                         ("evaluation_cases.json", "evaluation"),
                         ("draft_cases.json", "draft")):
        for case in json.loads((ec / fname).read_text(encoding="utf-8")):
            pf = run_preflight(case["draft"], "")
            res = run_coach(stage, case["draft"], preflight=pf, use_ai=False)
            sevs = [f["severity"] for f in res["findings"]]
            log(f"econlens {case['id']} [{stage}]: {len(res['findings'])} deterministic "
                f"finding(s) {sevs} (expected {case['expected']})")
    log(f"econlens cases done in {time.perf_counter() - t0:.2f}s (offline deterministic)")


# ------------------------------------------------------------ main

def main() -> None:
    t_all = time.perf_counter()
    convert()

    log("\n=== TierBridge: 300 students x 6 lessons (run A, timed) ===")
    times = run_pipeline(CONV / "run_a")
    log("  timings: " + ", ".join(f"{k}={v * 1000:.0f}ms" for k, v in times.items()))
    log(f"  pipeline total: {sum(times.values()):.2f}s")
    log("=== run B (determinism check) ===")
    run_pipeline(CONV / "run_b")

    log("\n=== verification ===")
    verify_tierbridge()

    size_json = (CONV / "run_a" / "class.json").stat().st_size
    size_html = (CONV / "run_a_trend.html").stat().st_size
    log(f"  data volume: class.json={size_json / 1024:.0f} KB, trend={size_html / 1024:.0f} KB, "
        f"1800 assignment records (300 x 6)")

    log("\n=== edulab ===")
    run_edulab()

    log("\n=== econlens fixture cases ===")
    run_econlens()

    log(f"\nALL DONE in {time.perf_counter() - t_all:.2f}s")
    (CONV / "stress_report.txt").write_text("\n".join(report), encoding="utf-8")


if __name__ == "__main__":
    main()
