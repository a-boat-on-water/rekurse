"""report.html, postmortem.md and the AGENTS.md block, rendered from a store only."""
from __future__ import annotations

import html
from pathlib import Path


def _cell(s, n):
    if not n:
        return '<td class="na">–</td>'
    frac = s / n
    hue = int(120 * frac)
    return f'<td style="background:hsl({hue}70% 45%);color:#fff">{s}/{n}</td>'


def _rates_by_cell(runs):
    """Key: (row_key, k). Sweep baseline and fresh decision baseline are separate rows so the
    wrong-turn definition and the decision never share runs."""
    cells: dict[tuple[str, int], list] = {}
    for r in runs:
        if r["lesson_id"]:
            key = r["lesson_id"]
        else:
            key = "base:decision" if r["purpose"] == "decision" else "base:sweep"
        cells.setdefault((key, r["checkpoint_k"]), []).append(r)
    return cells


def rescue_grid(store, doc) -> str:
    from .pipeline import rescue_rate
    runs = [r for r in store.runs(doc["run_group"]) if r["trap"] == doc["trap"]]
    cps = store.get_checkpoints(doc["session_id"])
    ks = [c["k"] for c in cps]
    cells = _rates_by_cell(runs)
    lessons = {L["_id"]: L for L in store.lessons(doc["run_group"])}
    rows = [("baseline (placebo), sweep", "base:sweep"), ("baseline (placebo), fresh seeds for decision", "base:decision")]
    rows += [(f"lesson {lid}", lid) for lid in doc.get("lesson_rates", {})]
    wt = doc["wrong_turn_k"]
    head = "".join(f'<th class="{"wt" if k == wt else ""}">k={k}{" hint" if c["is_hint"] else ""}</th>' for k, c in zip(ks, cps))
    body = []
    for label, lid in rows:
        tds = []
        for k in ks:
            s, n = rescue_rate(cells.get((lid, k), []))
            tds.append(_cell(s, n).replace("<td", '<td class="wt"', 1) if k == wt else _cell(s, n))
        is_lesson = lid in lessons
        text = html.escape(lessons[lid]["text"]) if is_lesson else ""
        status = lessons[lid]["status"] if is_lesson else ""
        body.append(f"<tr><th>{label}<br><small>{status}</small><div class='lt'>{text}</div></th>{''.join(tds)}</tr>")
    return f'<table class="grid"><tr><th></th>{head}</tr>{"".join(body)}</table>'


def headline(doc) -> str:
    ls, ln = doc["decision_lesson"]
    bs, bn = doc["decision_baseline"]
    p = doc["p_values"].get("wrong_turn")
    ho = ""
    if doc.get("heldout_with"):
        hs, hn = doc["heldout_with"]; ws, wn = doc["heldout_without"]
        ho = f" Held-out: {hs}/{hn} with vs {ws}/{wn} without (p={doc['p_values']['heldout']:.2f})."
    return (f"Wrong turn: checkpoint {doc['wrong_turn_k']} of {len(doc['probed_ks'])} probed. "
            f"Lesson rescues {ls}/{ln} vs fresh baseline {bs}/{bn} (one-sided Fisher p={p:.3f}).{ho} "
            f"<b>{doc['decision'].upper()}</b>")


def postmortem(store, doc) -> str:
    session = store.get_session(doc["session_id"])
    cps = store.get_checkpoints(doc["session_id"])
    wt = doc["wrong_turn_k"]
    cp = next((c for c in cps if c["k"] == wt), None)
    lessons = {L["_id"]: L for L in store.lessons(doc["run_group"])}
    best = lessons.get(doc.get("best_lesson_id") or "")
    lines = [f"# Post-mortem: {doc['trap']} ({doc['run_group']})", "",
             f"**What happened.** The agent needed {session['total_turns']} turns; a human hint arrived at turn "
             f"{session['hint_turn']} and it solved the task at turn {session['solved_turn']}.", "",
             f"**Where it went wrong.** Replaying from each checkpoint without help, the agent stopped recovering at "
             f"checkpoint {wt} (baseline rescue rates by checkpoint: "
             + ", ".join(f"k={k}: {s}/{n}" for k, (s, n) in doc["sweep_rates"].items()) + ")."]
    if cp:
        lines += ["", f"> **User (turn {wt}):** {cp['user_msg']}", ">",
                  f"> **Agent:** {(cp.get('agent_msg_excerpt') or '(no text)').strip()[:400]}"]
    if best:
        ls, ln = doc["decision_lesson"]; bs, bn = doc["decision_baseline"]
        lines += ["", f"**The lesson.** \"{best['text']}\"", "",
                  f"**Evidence.** At checkpoint {wt}: lesson {ls}/{ln} vs fresh baseline {bs}/{bn} "
                  f"(p={doc['p_values']['wrong_turn']:.3f})."]
        if doc.get("heldout_with"):
            hs, hn = doc["heldout_with"]; ws, wn = doc["heldout_without"]
            lines += [f"Held-out trap `{doc['heldout']}`: {hs}/{hn} with vs {ws}/{wn} without."]
    lines += ["", f"**Decision:** {doc['decision']}." + (" " + "; ".join(doc["failed_conditions"]) if doc["failed_conditions"] else "")]
    for L in lessons.values():
        if L["status"] in ("rejected", "merged") and L.get("reason"):
            lines.append(f"- Discarded lesson ({L['reason']}): \"{L['text']}\"")
    if doc.get("notes"):
        lines += ["", "Notes: " + "; ".join(doc["notes"])]
    return "\n".join(lines) + "\n"


def agents_block(store, doc) -> str:
    lessons = [L for L in store.lessons(doc["run_group"]) if L["status"] == "adopted"]
    if not lessons:
        return "## Proven lessons\n\n_None adopted yet._\n"
    ls, ln = doc["decision_lesson"]; bs, bn = doc["decision_baseline"]
    ev = f"rescued {ls}/{ln} vs {bs}/{bn} at turn {doc['wrong_turn_k']}"
    if doc.get("heldout_with"):
        hs, hn = doc["heldout_with"]; ws, wn = doc["heldout_without"]
        ev += f"; held-out {hs}/{hn} vs {ws}/{wn}"
    return "## Proven lessons\n\n" + "".join(f"- {L['text']}  \n  <!-- rekurse: {ev}; run {doc['run_group']} -->\n" for L in lessons)


CSS = """
body{font:15px/1.45 -apple-system,Helvetica,Arial,sans-serif;max-width:1100px;margin:32px auto;padding:0 16px;color:#1c1c1c}
h1{font-size:22px}.head{font-size:18px;padding:12px 16px;background:#f3f4f6;border-radius:8px}
table.grid{border-collapse:collapse;margin:20px 0}.grid th,.grid td{border:1px solid #ddd;padding:6px 10px;text-align:center;font-size:14px}
.grid th{text-align:left;background:#fafafa}.grid th.wt,.grid td.wt{outline:3px solid #111;outline-offset:-3px}
.na{color:#999;background:#f3f3f3}.lt{font-weight:normal;font-size:12px;color:#444;max-width:320px}
ul.lessons li{margin:6px 0}.tag{font-size:12px;padding:2px 6px;border-radius:4px;background:#eee;margin-left:6px}
"""


def render_html(store, doc) -> str:
    lessons = store.lessons(doc["run_group"])
    li = "".join(
        f'<li>"{html.escape(L["text"])}"<span class="tag">{L["status"]}</span>'
        + (f'<span class="tag">{html.escape(str(L["reason"]))}</span>' if L.get("reason") else "")
        + (f'<span class="tag">top-1 cos {L["top1_similarity"]}</span>' if L.get("top1_similarity") is not None else "")
        + "</li>" for L in lessons)
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Rekurse report</title><style>{CSS}</style></head><body>
<h1>Rekurse · {html.escape(doc['trap'])} · {html.escape(doc['run_group'])}</h1>
<div class="head">{headline(doc)}</div>
<h2>Rescue grid (n/N counted runs; gray = untested; outlined = wrong turn)</h2>
{rescue_grid(store, doc)}
<h2>Lessons</h2><ul class="lessons">{li}</ul>
<h2>Post-mortem</h2><pre style="white-space:pre-wrap">{html.escape(doc.get('postmortem_md', ''))}</pre>
</body></html>"""


def write_outputs(store, doc, out: Path) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    paths = [out / "report.html", out / "postmortem.md", out / "AGENTS.md"]
    paths[0].write_text(render_html(store, doc))
    paths[1].write_text(doc.get("postmortem_md") or postmortem(store, doc))
    paths[2].write_text(agents_block(store, doc))
    return paths
