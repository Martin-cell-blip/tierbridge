"""Next-lesson tier assignment from exit-ticket results - closes the teaching loop:

    generate pack -> teach -> exit ticket -> gap report -> ASSIGN -> next lesson

Rules (deterministic, printed on the sheet so the teacher can overrule them):

1. Tier comes from READINESS (mastery on the last exit ticket), never from EAL
   status:   mastery >= 0.8 -> t3;  >= 0.5 -> t2;  < 0.5 -> t1.
2. EAL is a separate LANGUAGE axis: EAL students keep glossary access at any
   tier. Being EAL never pushes a student down a tier.
3. With a previous assignment, students move at most ONE tier per cycle.
4. Anti-crutch rule: a t1 student who reaches mastery >= 0.8 MUST move up -
   succeeding with full scaffolds twice in a row means the scaffold is now a
   ceiling, not a bridge.
"""
from __future__ import annotations

import csv
import html
from pathlib import Path

from .gap import load_results

TIER_ORDER = ("t1", "t2", "t3")
TIER_NAMES = {"t1": "Bridge / Foundation", "t2": "Core", "t3": "Stretch / Extension"}
HI, LO = 0.8, 0.5


def _base_tier(mastery: float) -> str:
    if mastery >= HI:
        return "t3"
    if mastery >= LO:
        return "t2"
    return "t1"


def _step_limit(prev: str, target: str) -> str:
    """Move at most one tier from the previous assignment."""
    pi, ti = TIER_ORDER.index(prev), TIER_ORDER.index(target)
    if ti > pi + 1:
        return TIER_ORDER[pi + 1]
    if ti < pi - 1:
        return TIER_ORDER[pi - 1]
    return target


def load_previous(path: str | Path) -> dict[str, str]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "student" not in reader.fieldnames or "tier" not in reader.fieldnames:
            raise ValueError("previous-assignments CSV needs columns: student, tier")
        out = {}
        for row in reader:
            tier = row["tier"].strip()
            if tier not in TIER_ORDER:
                raise ValueError(f"unknown tier {tier!r} for {row['student']!r}")
            out[row["student"].strip()] = tier
        return out


def assign(rows: list[dict], previous: dict[str, str] | None = None) -> list[dict]:
    previous = previous or {}
    out = []
    for r in rows:
        scores = r["scores"]
        mastery = sum(scores.values()) / len(scores)
        target = _base_tier(mastery)
        prev = previous.get(r["student"])
        notes = []
        if prev:
            limited = _step_limit(prev, target)
            if limited != target:
                notes.append(f"move limited to one step from {prev}")
                target = limited
            if prev == "t1" and mastery >= HI:
                target = "t2"
                notes.append("anti-crutch: mastered with full scaffolds - must move up")
            elif prev == target:
                notes.append("stays")
            elif TIER_ORDER.index(target) > TIER_ORDER.index(prev):
                notes.append("moves up")
            else:
                notes.append("moves down - re-teach before re-testing")
        out.append({
            "student": r["student"],
            "group": r["group"],
            "mastery": round(mastery, 3),
            "tier": target,
            "language_support": r["group"] == "EAL",
            "notes": "; ".join(notes) or "first assignment",
        })
    return out


def write_assignments_csv(assignments: list[dict], path: str | Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["student", "group", "mastery", "tier",
                                               "language_support", "notes"])
        writer.writeheader()
        writer.writerows(assignments)


def render_grouping_sheet(assignments: list[dict], title: str = "Next-lesson tier groups") -> str:
    boxes = []
    for tid in TIER_ORDER:
        members = [a for a in assignments if a["tier"] == tid]
        rows = "".join(
            "<li>{name}{lang} <span class='m'>({mastery:.0%}{note})</span></li>".format(
                name=html.escape(a["student"]),
                lang=" *" if a["language_support"] else "",
                mastery=a["mastery"],
                note=", " + html.escape(a["notes"]) if a["notes"] != "first assignment" else "")
            for a in members)
        boxes.append(
            f"<div class='box {tid}'><h2>{TIER_NAMES[tid]} <span class='n'>({len(members)})</span></h2>"
            f"<ul>{rows or '<li><i>none</i></li>'}</ul></div>")
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>body{{font-family:Georgia,serif;max-width:860px;margin:30px auto;padding:0 20px;color:#111}}
.grid{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px}}
.box{{border:2px solid #999;border-radius:8px;padding:10px 14px}}
.box h2{{font-size:1rem;margin:0 0 6px}}
.t1{{border-color:#8a5a00}}.t2{{border-color:#1f5e49}}.t3{{border-color:#28437c}}
ul{{margin:0;padding-left:18px;font-size:.9rem}}li{{margin:3px 0}}.m{{color:#666;font-size:.8rem}}
.n{{color:#666;font-weight:400}}
.rules{{background:#f4f1e8;border-left:4px solid #8a5a00;padding:8px 14px;font-size:.85rem;margin-top:16px}}
@media print{{.box{{break-inside:avoid}}}}</style></head><body>
<h1 style="font-size:1.3rem">{html.escape(title)}</h1>
<p style="font-size:.85rem;color:#555">* = EAL: keeps glossary access at every tier. Tier comes from last
exit-ticket mastery, never from EAL status. Teacher judgment overrides this sheet.</p>
<div class="grid">{''.join(boxes)}</div>
<div class="rules"><b>Rules used:</b> mastery ≥80% → Stretch; 50–79% → Core; &lt;50% → Bridge.
Max one tier move per cycle. Bridge students who reach ≥80% must move up (anti-crutch).
A student moving down means re-teach, not just re-tier.</div>
</body></html>"""
