"""Render the worksheet pack to a single printable HTML file (A4, page-break per sheet)."""
from __future__ import annotations

import html
from datetime import date

CSS = """
body{font-family:Georgia,'Times New Roman',serif;color:#111;margin:0;background:#eee;}
.sheet{background:#fff;max-width:186mm;margin:10mm auto;padding:14mm 16mm;box-shadow:0 1px 6px rgba(0,0,0,.15);}
@media print{
  body{background:#fff}
  .sheet{box-shadow:none;margin:0;max-width:none;page-break-after:always}
  .no-print{display:none}
}
h1{font-size:15pt;margin:0 0 2mm} h2{font-size:12pt;margin:6mm 0 2mm;border-bottom:1.5pt solid #1f5e49;padding-bottom:1mm}
.tierband{display:inline-block;padding:1mm 4mm;border-radius:2mm;color:#fff;font-weight:700;font-size:9pt}
.t1 .tierband{background:#8a5a00}.t2 .tierband{background:#1f5e49}.t3 .tierband{background:#28437c}
.obj{border:1.5pt solid #1f5e49;border-radius:2mm;padding:3mm 5mm;margin:4mm 0;font-size:10.5pt}
.obj b{color:#1f5e49}
table{border-collapse:collapse;width:100%;font-size:10pt;margin:3mm 0}
th,td{border:.8pt solid #999;padding:2mm 3mm;text-align:left;vertical-align:top}
th{background:#eef3ef}
.task{border:.8pt solid #bbb;border-radius:2mm;padding:3mm 5mm;margin:4mm 0}
.task h3{font-size:11pt;margin:0 0 2mm}
.frames{background:#f4f1e8;border-left:3pt solid #8a5a00;padding:2mm 4mm;margin:2mm 0;font-size:10pt}
.frames b{font-size:9pt;letter-spacing:.05em}
.lines{border-bottom:.8pt solid #999;height:8mm}
.meta{font-size:9pt;color:#555}
.shell{color:#8a5a00;font-style:italic}
.notes{background:#eef3ef;border-radius:2mm;padding:3mm 5mm;font-size:10pt}
ul{margin:2mm 0 2mm 5mm;padding:0}li{margin:1mm 0}
.review-flag{background:#fdecec;border:1pt solid #c0392b;color:#c0392b;padding:2mm 4mm;font-size:9.5pt;border-radius:2mm;margin:3mm 0}
"""


def _e(s) -> str:
    return html.escape(str(s))


def _glossary_table(lesson: dict, bilingual: bool) -> str:
    head = "<tr><th>Term</th><th>Meaning</th>" + ("<th>中文</th>" if bilingual else "") + "</tr>"
    rows = "".join(
        f"<tr><td><b>{_e(t['term'])}</b></td><td>{_e(t['definition'])}</td>"
        + (f"<td>{_e(t.get('zh', ''))}</td>" if bilingual else "")
        + "</tr>"
        for t in lesson["key_terms"])
    return f"<h2>Glossary</h2><table>{head}{rows}</table>"


def _task_html(task: dict) -> str:
    frames = task.get("frames") or []
    frames_html = ""
    if frames:
        frames_html = ("<div class='frames'><b>SENTENCE STARTERS</b><br>"
                       + "<br>".join(_e(f) for f in frames) + "</div>")
    shell = "<div class='shell'>[Template shell — teacher completes this prompt]</div>" if task.get("template_shell") else ""
    return (f"<div class='task'><h3>{_e(task['title'])}</h3>"
            f"<p>{_e(task['instructions'])}</p>{shell}{frames_html}"
            "<div class='lines'></div><div class='lines'></div></div>")


def _worksheet(pack: dict, tid: str) -> str:
    lesson, tier = pack["lesson"], pack["tiers"][tid]
    gloss = _glossary_table(lesson, tier["glossary_bilingual"]) if tier["glossary"] else ""
    sc = "".join(f"<li>{_e(c)}</li>" for c in lesson["success_criteria"])
    tasks = "".join(_task_html(t) for t in tier["tasks"])
    return f"""<div class="sheet {tid}">
<h1>{_e(lesson['topic'])} <span class="tierband">{_e(tier['name'])}</span></h1>
<p class="meta">{_e(lesson['subject'])} · Name: ______________ · Date: ______________</p>
<div class="obj"><b>Learning objective (same for the whole class):</b> {_e(lesson['objective'])}
<ul>{sc}</ul></div>
{gloss}
<h2>Tasks</h2>{tasks}
</div>"""


def _exit_ticket(pack: dict, tid: str) -> str:
    lesson = pack["lesson"]
    tier = pack["tiers"][tid]
    qs = []
    for q in pack["exit_ticket"]:
        frames = q["frames"].get(tid) or []
        frames_html = ("<div class='frames'>" + "<br>".join(_e(f) for f in frames) + "</div>") if frames else ""
        qs.append(f"<div class='task'><h3>Q{q['n']} ({_e(q['function'])})</h3>"
                  f"<p>{_e(q['question'])}</p>{frames_html}"
                  "<div class='lines'></div><div class='lines'></div></div>")
    return f"""<div class="sheet {tid}">
<h1>Exit ticket — {_e(lesson['topic'])} <span class="tierband">{_e(tier['name'])}</span></h1>
<p class="meta">Same questions for every tier — only the support differs. Name: ______________</p>
{''.join(qs)}
</div>"""


def _teacher_notes(pack: dict) -> str:
    lesson = pack["lesson"]
    moves = "".join(
        f"<h2>{pack['tiers'][tid]['name']} ({tid})</h2><p class='meta'>{_e(pack['tiers'][tid]['audience'])} — "
        f"{_e(pack['tiers'][tid]['principle'])}</p><ul>"
        + "".join(f"<li>{_e(m)}</li>" for m in pack["tiers"][tid]["teacher_moves"]) + "</ul>"
        for tid in ("t1", "t2", "t3"))
    answers = "".join(
        f"<tr><td>Q{q['n']}</td><td>{_e(q['question'])}</td><td>{_e(q['answer_note'] or '—')}</td></tr>"
        for q in pack["exit_ticket"])
    review = ("<div class='review-flag'><b>AI-drafted tasks — review before class.</b> "
              "Check every task against the objective and your students before printing.</div>"
              if lesson.get("ai_drafted") else "")
    mode_note = ("Template mode: task prompts are shells for you to complete."
                 if pack["mode"] == "template" else "Authored mode: tasks came from the lesson file.")
    return f"""<div class="sheet">
<h1>Teacher notes — {_e(lesson['topic'])}</h1>
<p class="meta">{_e(lesson['subject'])} · generated {date.today().isoformat()} · {_e(mode_note)}</p>
{review}
<div class="obj"><b>Objective:</b> {_e(lesson['objective'])}</div>
{moves}
<h2>Scaffold fading</h2><div class="notes">{_e(pack['fading_note'])}</div>
<h2>Exit ticket answer notes</h2>
<table><tr><th>Q</th><th>Question</th><th>What a mastery answer contains</th></tr>{answers}</table>
<h2>Recording results</h2>
<div class="notes">Score each exit-ticket question 1 (mastered) or 0. Record one row per student in a CSV:
<code>student,group,q1,q2,q3</code> where group is <code>EAL</code> or <code>non-EAL</code>.
Then run <code>python -m tierbridge gap results.csv</code> to see the mastery gap.</div>
</div>"""


def render_pack(pack: dict) -> str:
    parts = [_teacher_notes(pack)]
    for tid in ("t1", "t2", "t3"):
        parts.append(_worksheet(pack, tid))
    for tid in ("t1", "t2", "t3"):
        parts.append(_exit_ticket(pack, tid))
    title = f"TierBridge — {pack['lesson']['topic']}"
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{_e(title)}</title>"
            f"<style>{CSS}</style></head><body>"
            f"<p class='no-print' style='text-align:center;font-size:10pt;color:#555'>"
            f"Print with Ctrl+P — each sheet is one A4 page.</p>"
            + "".join(parts) + "</body></html>")
