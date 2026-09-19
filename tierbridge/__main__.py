"""TierBridge CLI.

Usage:
  python -m tierbridge generate <lesson.yaml> [-o out/] [--ai]
  python -m tierbridge gap <results.csv> [-o out/] [--threshold 0.67]
  python -m tierbridge assign <results.csv> [-o out/] [--previous assignments.csv]
  python -m tierbridge class init <name> --roster roster.csv --dir classes/10B
  python -m tierbridge class record <class_dir> <results.csv> [--lesson lesson.yaml]
                                    [--overrides overrides.csv] [--topic "..."]
  python -m tierbridge class trend <class_dir> [-o out/]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import llm
from .gap import analyze, load_results, render_gap_report
from .generate import build_pack, enrich_with_ai
from .models import load_lesson
from .render import render_pack


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="tierbridge")
    sub = parser.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="build the tiered worksheet pack")
    g.add_argument("lesson")
    g.add_argument("-o", "--out", default="out")
    g.add_argument("--ai", action="store_true",
                   help="draft tier tasks with the configured LLM (TIERBRIDGE_API_KEY)")

    p = sub.add_parser("gap", help="mastery-gap report from an exit-ticket results CSV")
    p.add_argument("results")
    p.add_argument("-o", "--out", default="out")
    p.add_argument("--threshold", type=float, default=2 / 3)

    a = sub.add_parser("assign", help="next-lesson tier assignment from exit-ticket results")
    a.add_argument("results")
    a.add_argument("-o", "--out", default="out")
    a.add_argument("--previous", help="previous assignments CSV (student,tier) for movement rules")

    c = sub.add_parser("class", help="class persistence: roster, lesson history, learning trend")
    csub = c.add_subparsers(dest="class_cmd", required=True)
    ci = csub.add_parser("init")
    ci.add_argument("name")
    ci.add_argument("--roster", required=True)
    ci.add_argument("--dir", required=True)
    cr = csub.add_parser("record")
    cr.add_argument("class_dir")
    cr.add_argument("results")
    cr.add_argument("--lesson", help="lesson.yaml - functions from its exit ticket")
    cr.add_argument("--items", help="CSV item,function - unified assessment map (overrides --lesson functions)")
    cr.add_argument("--overrides", help="CSV student,tier,reason - teacher overrides")
    cr.add_argument("--topic", default="")
    ct = csub.add_parser("trend")
    ct.add_argument("class_dir")
    ct.add_argument("-o", "--out", default="out")

    args = parser.parse_args(argv)
    out_dir = None
    if getattr(args, "out", None):
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)

    if args.cmd == "generate":
        lesson = load_lesson(args.lesson)
        if args.ai:
            if not llm.is_configured():
                print("--ai requested but TIERBRIDGE_API_KEY is not set", file=sys.stderr)
                return 2
            lesson = enrich_with_ai(lesson, llm.chat)
            print("AI drafted the tier tasks - review flag added to teacher notes.")
        pack = build_pack(lesson)
        out = out_dir / (Path(args.lesson).stem + "_pack.html")
        out.write_text(render_pack(pack), encoding="utf-8")
        print(f"[{pack['mode']} mode] worksheet pack -> {out}")
        return 0

    if args.cmd == "gap":
        analysis = analyze(load_results(args.results), threshold=args.threshold)
        out = out_dir / (Path(args.results).stem + "_gap.html")
        out.write_text(render_gap_report(analysis), encoding="utf-8")
        gap = analysis["gap_pp"]
        print(f"mastery gap: {gap if gap is not None else 'n/a'} pp -> {out}")
        return 0

    if args.cmd == "assign":
        from .assign import assign as do_assign
        from .assign import load_previous, render_grouping_sheet, write_assignments_csv
        rows = load_results(args.results)
        previous = load_previous(args.previous) if args.previous else None
        assignments = do_assign(rows, previous)
        stem = Path(args.results).stem
        csv_out = out_dir / f"{stem}_assignments.csv"
        html_out = out_dir / f"{stem}_groups.html"
        write_assignments_csv(assignments, csv_out)
        html_out.write_text(render_grouping_sheet(assignments), encoding="utf-8")
        counts = {t: sum(1 for a in assignments if a["tier"] == t) for t in ("t1", "t2", "t3")}
        print(f"assigned {len(assignments)} students "
              f"(t1={counts['t1']}, t2={counts['t2']}, t3={counts['t3']}) -> {html_out}")
        return 0

    if args.cmd == "class":
        from .classroom import init_class, load_class, record_lesson
        from .trend import render_trend
        if args.class_cmd == "init":
            cls = init_class(args.name, args.roster, args.dir)
            print(f"class '{cls['name']}' created with {len(cls['roster'])} students -> {args.dir}")
            return 0
        if args.class_cmd == "record":
            session = record_lesson(args.class_dir, args.results,
                                    lesson_yaml=args.lesson, items_csv=args.items,
                                    overrides_csv=args.overrides, topic=args.topic)
            gap = session["gap"]["gap_pp"]
            n_over = sum(1 for a in session["assignments"] if a["override"])
            print(f"lesson {session['n']} recorded: {len(session['assignments'])} results, "
                  f"{len(session['absent'])} absent, gap "
                  f"{'n/a' if gap is None else f'{gap:+.1f} pp'}, {n_over} override(s)")
            return 0
        if args.class_cmd == "trend":
            cls = load_class(args.class_dir)
            out = out_dir / f"{Path(args.class_dir).name}_trend.html"
            out.write_text(render_trend(cls), encoding="utf-8")
            from .classroom import convergence_verdict
            v = convergence_verdict(cls)
            print(f"trend over {len(cls['sessions'])} lesson(s): {v['verdict']} -> {out}")
            return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
