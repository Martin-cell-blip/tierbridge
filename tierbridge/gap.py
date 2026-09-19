"""Mastery-gap analysis from exit-ticket results.

CSV schema: student,group,q1,q2,...   (group: EAL / non-EAL; items scored 0/1)
Mastery = a student answers >= threshold share of items correctly (default 2/3).
The headline number is the gap in mastery rate between non-EAL and EAL students.
"""
from __future__ import annotations

import csv
import html
from pathlib import Path

GROUPS = ("EAL", "non-EAL")
DEFAULT_THRESHOLD = 2 / 3


class ResultsError(ValueError):
    pass


def load_results(path: str | Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames or []
        qcols = [c for c in fields if c.lower().startswith("q") and c[1:].isdigit()]
        if "student" not in fields or "group" not in fields or not qcols:
            raise ResultsError("CSV needs columns: student, group, q1..qN")
        rows = []
        for i, row in enumerate(reader):
            group = (row["group"] or "").strip()
            if group not in GROUPS:
                raise ResultsError(f"row {i + 2}: group must be one of {GROUPS}, got {group!r}")
            scores = {}
            for c in qcols:
                v = (row[c] or "").strip()
                if v not in ("0", "1"):
                    raise ResultsError(f"row {i + 2}: {c} must be 0 or 1, got {v!r}")
                scores[c] = int(v)
            rows.append({"student": row["student"].strip(), "group": group, "scores": scores})
    if not rows:
        raise ResultsError("no data rows")
    return rows


def analyze(rows: list[dict], threshold: float = DEFAULT_THRESHOLD) -> dict:
    qcols = sorted(rows[0]["scores"], key=lambda c: int(c[1:]))
    by_group: dict[str, list[dict]] = {g: [r for r in rows if r["group"] == g] for g in GROUPS}

    def mastery_rate(group_rows: list[dict]) -> float | None:
        if not group_rows:
            return None
        mastered = sum(
            1 for r in group_rows
            if sum(r["scores"].values()) / len(r["scores"]) >= threshold)
        return mastered / len(group_rows)

    def item_rate(group_rows: list[dict], q: str) -> float | None:
        if not group_rows:
            return None
        return sum(r["scores"][q] for r in group_rows) / len(group_rows)

    group_stats = {
        g: {"n": len(by_group[g]),
            "mastery_rate": mastery_rate(by_group[g]),
            "items": {q: item_rate(by_group[g], q) for q in qcols}}
        for g in GROUPS
    }
    gap_pp = None
    if group_stats["EAL"]["mastery_rate"] is not None and group_stats["non-EAL"]["mastery_rate"] is not None:
        gap_pp = round(
            (group_stats["non-EAL"]["mastery_rate"] - group_stats["EAL"]["mastery_rate"]) * 100, 1)
    item_gaps = {}
    for q in qcols:
        a, b = group_stats["non-EAL"]["items"][q], group_stats["EAL"]["items"][q]
        item_gaps[q] = None if a is None or b is None else round((a - b) * 100, 1)
    return {"threshold": threshold, "questions": qcols, "n": len(rows),
            "groups": group_stats, "gap_pp": gap_pp, "item_gaps": item_gaps}


# ---------------------------------------------------------------- HTML report

def _bar(pct: float | None, color: str) -> str:
    if pct is None:
        return "<i>no students</i>"
    w = round(pct * 100)
    return (f"<svg width='220' height='16'><rect width='220' height='16' fill='#eee'/>"
            f"<rect width='{w * 2.2:.0f}' height='16' fill='{color}'/></svg> {w}%")


def render_gap_report(analysis: dict, title: str = "Exit-ticket mastery gap") -> str:
    g = analysis["groups"]
    gap = analysis["gap_pp"]
    if gap is None:
        headline = "Gap not computable (one group is empty)."
    else:
        direction = "non-EAL ahead" if gap > 0 else ("EAL ahead" if gap < 0 else "no gap")
        headline = f"Mastery gap: <strong>{abs(gap):.1f} pp</strong> ({direction})."
    item_rows = "".join(
        "<tr><td>{q}</td><td>{e}</td><td>{n}</td><td>{d}</td></tr>".format(
            q=q,
            e=_bar(g["EAL"]["items"][q], "#8a5a00"),
            n=_bar(g["non-EAL"]["items"][q], "#1f5e49"),
            d=("—" if analysis["item_gaps"][q] is None else f"{analysis['item_gaps'][q]:+.1f} pp"))
        for q in analysis["questions"])
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>body{{font-family:Georgia,serif;max-width:760px;margin:40px auto;padding:0 20px;color:#111}}
table{{border-collapse:collapse;width:100%;font-size:.9rem}}th,td{{border:1px solid #bbb;padding:6px 10px;text-align:left}}
th{{background:#eef3ef}}.headline{{font-size:1.05rem;background:#eef3ef;padding:12px 16px;border-radius:8px}}
.note{{background:#f4f1e8;border-left:4px solid #8a5a00;padding:8px 14px;font-size:.85rem}}</style></head><body>
<h1 style="font-size:1.4rem">{html.escape(title)}</h1>
<p class="headline">{headline}</p>
<table>
<tr><th>Group</th><th>Students</th><th>Mastery rate (≥{analysis['threshold']:.0%} of items)</th></tr>
<tr><td>EAL</td><td>{g['EAL']['n']}</td><td>{_bar(g['EAL']['mastery_rate'], '#8a5a00')}</td></tr>
<tr><td>non-EAL</td><td>{g['non-EAL']['n']}</td><td>{_bar(g['non-EAL']['mastery_rate'], '#1f5e49')}</td></tr>
</table>
<h2 style="font-size:1.05rem">Per question</h2>
<table><tr><th>Q</th><th>EAL correct</th><th>non-EAL correct</th><th>Gap</th></tr>{item_rows}</table>
<div class="note">Read with care: one lesson's exit ticket is a noisy signal, and class sizes are small.
Track the gap across lessons; the goal is convergence over a term, not a single good day.
If EAL scores rise only while scaffolds are present, fade the scaffolds and re-check.</div>
</body></html>"""
