"""Cross-lesson trend report (HTML): the instructional-decision view.

Answers, on one page:
  1. per student - where they are, how they moved, and WHY (rule note / override)
  2. per class   - is the EAL gap converging, overall and by question function
"""
from __future__ import annotations

import html

from .assign import TIER_NAMES
from .classroom import convergence_verdict, function_trend, student_timeline

TIER_COLOR = {"t1": "#8a5a00", "t2": "#1f5e49", "t3": "#28437c"}


def _e(s) -> str:
    return html.escape(str(s))


def _arrow(prev: float | None, cur: float) -> str:
    if prev is None:
        return ""
    if cur <= prev - 3:
        return " ↓"       # gap shrinking = good
    if cur >= prev + 3:
        return " ↑"       # gap widening
    return " →"


def _tier_chip(tier: str | None, mastery: float | None, absent: bool) -> str:
    if absent:
        return "<td class='cell absent'>absent</td>"
    if tier is None:
        return "<td class='cell'>—</td>"
    return (f"<td class='cell'><span class='chip' style='background:{TIER_COLOR[tier]}'>"
            f"{_e(TIER_NAMES[tier].split(' / ')[0])}</span><br>"
            f"<span class='m'>{mastery:.0%}</span></td>")


def render_trend(cls: dict) -> str:
    sessions = cls["sessions"]
    n_lessons = len(sessions)
    verdict = convergence_verdict(cls)
    fn_trend = function_trend(cls)

    # ---- class gap table
    gap_rows = []
    prev_gap = None
    for s in sessions:
        g = s["gap"]["gap_pp"]
        gap_rows.append(
            f"<tr><td>L{s['n']}</td><td>{_e(s['lesson'].get('topic', '') or '—')}</td>"
            f"<td>{'—' if g is None else f'{g:+.1f} pp' + _arrow(prev_gap, g)}</td>"
            f"<td>{len(s['absent'])}</td></tr>")
        if g is not None:
            prev_gap = g

    # ---- by-function trend
    fn_rows = []
    for fn, series in sorted(fn_trend.items()):
        cells = []
        prev = None
        for n, gap in series:
            cells.append(f"L{n}: {gap:+.1f}{_arrow(prev, gap)}")
            prev = gap
        fn_rows.append(f"<tr><td>{_e(fn)}</td><td>{' &nbsp; '.join(cells)}</td></tr>")

    # ---- per-student grid
    header_cells = "".join(f"<th>L{s['n']}</th>" for s in sessions)
    student_rows = []
    for r in sorted(cls["roster"], key=lambda x: x["student"]):
        tl = student_timeline(cls, r["student"])
        cells = "".join(_tier_chip(t["tier"], t["mastery"], t["absent"]) for t in tl)
        latest_note = next((t["notes"] for t in reversed(tl) if t["notes"]), "")
        override_mark = " <b style='color:#c0392b'>†</b>" if any(t["override"] for t in tl) else ""
        student_rows.append(
            f"<tr><td class='name'>{_e(r['student'])}{' *' if r['eal'] else ''}{override_mark}</td>"
            f"{cells}<td class='why'>{_e(latest_note)}</td></tr>")

    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>Learning trend — {_e(cls['name'])}</title>
<style>
body{{font-family:Georgia,serif;max-width:980px;margin:30px auto;padding:0 20px;color:#111}}
h1{{font-size:1.35rem}}h2{{font-size:1.05rem;border-bottom:2px solid #1f5e49;padding-bottom:3px}}
table{{border-collapse:collapse;width:100%;font-size:.87rem;margin:10px 0 22px}}
th,td{{border:1px solid #bbb;padding:5px 9px;text-align:left;vertical-align:top}}
th{{background:#eef3ef}}
.cell{{text-align:center}}.chip{{color:#fff;border-radius:4px;padding:1px 7px;font-size:.75rem;font-weight:700}}
.m{{color:#555;font-size:.78rem}}.absent{{color:#999;font-style:italic}}
.name{{font-weight:700;white-space:nowrap}}.why{{font-size:.78rem;color:#555;max-width:220px}}
.verdict{{padding:10px 16px;border-radius:8px;font-size:.95rem;margin:12px 0}}
.converging{{background:#e4efe8;border-left:5px solid #1f5e49}}
.widening{{background:#fdecec;border-left:5px solid #c0392b}}
.flat,.insufficient{{background:#f4f1e8;border-left:5px solid #8a5a00}}
.legend{{font-size:.8rem;color:#555}}
</style></head><body>
<h1>Learning trend — {_e(cls['name'])}</h1>
<p class="legend">{len(cls['roster'])} students · {n_lessons} lesson(s) recorded ·
* = EAL (language support at every tier) · † = teacher override on record ·
gap arrows: ↓ narrowing (good) / → flat / ↑ widening</p>

<div class="verdict {verdict['verdict'].split()[0]}"><b>Gap convergence: {verdict['verdict']}.</b>
{_e(verdict['detail'])}</div>

<h2>Class EAL gap by lesson</h2>
<table><tr><th>Lesson</th><th>Topic</th><th>Mastery gap (non-EAL − EAL)</th><th>Absent</th></tr>
{''.join(gap_rows)}</table>

<h2>Gap by question function</h2>
{'<table><tr><th>Function</th><th>Gap per lesson (pp)</th></tr>' + ''.join(fn_rows) + '</table>'
 if fn_rows else "<p class='legend'>Record lessons with <code>--lesson lesson.yaml</code> to break the gap down by question function (define / calculate / interpret ...).</p>"}

<h2>Per-student timeline</h2>
<table><tr><th>Student</th>{header_cells}<th>Latest movement rationale</th></tr>
{''.join(student_rows)}</table>

<p class="legend">Every tier move is explained by the rule note or a teacher override —
if a row surprises you, the note column says why the system did what it did, and the
override column says why a human disagreed. One exit ticket is a noisy signal: judge
trends over lessons, not single cells.</p>
</body></html>"""
