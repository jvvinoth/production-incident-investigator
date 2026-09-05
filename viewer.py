"""Demo viewer for the incident investigator - NOT part of the submission.

    python3 viewer.py            ->  http://localhost:8000

Runs investigate_verbose() on both incidents and renders the reports side
by side with the per-axis corroboration table. Each panel has an editable
query so you can show that the verdict is driven by the corpus, not by
the wording of the question. Standard library only.
"""
from __future__ import annotations

import html
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from data.loader import load_incident   # noqa: E402
import solution                          # noqa: E402

INCIDENTS = ["incident_a_pool_exhaustion", "incident_b_ambiguous_delay"]
PORT = 8000

CSS = """
:root{--bg:#f6f5f1;--card:#fff;--ink:#1e1e1c;--muted:#6b6a65;--line:#e2e0d8;
--ok:#1d9e75;--okbg:#e1f5ee;--warn:#ba7517;--warnbg:#faeeda;--bad:#a32d2d;--badbg:#fcebeb;--acc:#534ab7;--accbg:#eeedfe}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
header{padding:20px 28px 8px}h1{margin:0;font-size:20px;font-weight:500}header p{margin:4px 0 0;color:var(--muted)}
main{display:grid;grid-template-columns:1fr 1fr;gap:20px;padding:16px 28px 40px}@media(max-width:1000px){main{grid-template-columns:1fr}}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px}
.card h2{margin:0 0 4px;font-size:16px;font-weight:500}.sub{color:var(--muted);font-size:12px;margin-bottom:14px}
form textarea{width:100%;min-height:64px;border:1px solid var(--line);border-radius:8px;padding:8px 10px;font:13px/1.45 inherit;resize:vertical;background:#fbfaf7}
form button{margin-top:6px;border:1px solid var(--line);background:#fff;border-radius:8px;padding:6px 12px;font:13px inherit;cursor:pointer}
.score{display:flex;align-items:center;gap:16px;margin:18px 0 6px}.num{font-size:44px;font-weight:500;line-height:1}
.pill{display:inline-block;padding:3px 10px;border-radius:999px;font-size:12px;font-weight:500}
.ok{color:var(--ok);background:var(--okbg)}.warn{color:var(--warn);background:var(--warnbg)}.bad{color:var(--bad);background:var(--badbg)}.acc{color:var(--acc);background:var(--accbg)}
.facts{display:grid;grid-template-columns:auto 1fr;gap:4px 14px;margin:12px 0 16px;font-size:13px}.facts dt{color:var(--muted)}.facts dd{margin:0}
code{font:12px ui-monospace,Menlo,monospace;background:#f1efe8;padding:1px 5px;border-radius:4px}
table{width:100%;border-collapse:collapse;font-size:13px;margin:6px 0 16px}th{text-align:left;color:var(--muted);font-weight:500;padding:6px 8px;border-bottom:1px solid var(--line)}
td{padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}tr.miss td{color:var(--muted)}
.mark{display:inline-block;width:44px;text-align:center;border-radius:6px;font-size:11px;font-weight:500;padding:2px 0}
h3{font-size:13px;font-weight:500;color:var(--muted);margin:16px 0 6px;text-transform:uppercase;letter-spacing:.04em}
.text{margin:0;white-space:pre-wrap}.ev{border-left:3px solid var(--line);padding:6px 10px;margin:6px 0;font-size:13px}
.ev.neg{border-left-color:var(--warn)}.ev .src{display:block;font-size:11px;color:var(--muted);margin-bottom:2px}
.math{font-size:12px;color:var(--muted)}ul.nom{margin:0;padding-left:18px;font-size:13px}
"""


def esc(x) -> str:
    return html.escape(str(x))


def render_panel(name: str, query: str, default_query: str) -> str:
    _, corpus = load_incident(name)
    report, h = solution.investigate_verbose(query, corpus)
    conf = report["confidence_score"]
    tone = "ok" if conf >= 75 else ("warn" if conf >= 50 else "bad")
    review = report["needs_human_review"]

    rows = []
    for a in h.axes.values():
        cls = "hit" if a.hit else "miss"
        mark = f'<span class="mark {"ok" if a.hit else "bad"}">{"HIT" if a.hit else "miss"}</span>'
        detail = " ".join(filter(None, [a.strength, "· hedged" if a.hedged else ""]))
        src = a.units[0].source if a.units else ""
        rows.append(f"<tr class='{cls}'><td>{mark}</td><td>{esc(a.name)}</td>"
                    f"<td>{esc(detail)}</td><td>{a.weight()}</td><td><code>{esc(src)}</code></td></tr>")

    penalty = min(solution.HEDGE_PENALTY_CAP, solution.HEDGE_PENALTY_PER_SOURCE * len(h.hedge_sources()))
    math = (f"Σ axes = {h.raw_score()} &nbsp;−&nbsp; hedge penalty {penalty} "
            f"({len(h.hedge_sources())} source{'s' if len(h.hedge_sources()) != 1 else ''}: "
            f"{esc(', '.join(sorted(h.hedge_sources())) or 'none')}) &nbsp;→&nbsp; "
            f"clamp [{solution.FLOOR}, {solution.CAP}] = <b>{conf:g}</b>")

    counter_ids = {u.uid for u in h.counter}
    ev_units = {u.uid: u for a in h.axes.values() for u in a.units}
    ev_units.update({u.uid: u for u in h.symptom + h.coupled + h.counter})
    evidence = []
    for e in report["supporting_evidence"]:
        neg = any(u.source == e["source"] and u.text.startswith(e["excerpt"].rstrip(".")[:40]) and u.uid in counter_ids
                  for u in ev_units.values())
        evidence.append(f"<div class='ev{' neg' if neg else ''}'><span class='src'>{esc(e['source'])}"
                        f"{' · counter-evidence' if neg else ''}</span>{esc(e['excerpt'])}</div>")

    nominees = "".join(f"<li><code>{esc(c)}</code> {s:.2f}{' ← chosen' if c == h.component else ''}</li>"
                       for c, s in h.nominees[:5])
    changed = query.strip() != default_query.strip()

    return f"""
<section class="card">
  <h2>{esc(name)}</h2>
  <div class="sub">{'custom query' if changed else 'query from query.txt'}</div>
  <form method="get">
    <input type="hidden" name="incident" value="{esc(name)}">
    <textarea name="q">{esc(query)}</textarea>
    <button type="submit">Re-run with this query</button>
    {'<a href="/" style="margin-left:8px;font-size:13px">reset</a>' if changed else ''}
  </form>

  <div class="score">
    <div class="num" style="color:var(--{'ok' if tone == 'ok' else ('warn' if tone == 'warn' else 'bad')})">{conf:g}</div>
    <div>
      <div><span class="pill {'bad' if review else 'ok'}">{'needs human review' if review else 'confident'}</span></div>
      <div class="math" style="margin-top:6px">{math}</div>
    </div>
  </div>

  <dl class="facts">
    <dt>component</dt><dd><code>{esc(h.component)}</code></dd>
    <dt>signature</dt><dd>{esc(' / '.join(h.strong_sig) if h.strong_sig else ', '.join(h.weak_sig) or '—')}</dd>
    <dt>impacted</dt><dd>{' '.join(f'<code>{esc(s)}</code>' for s in report['impacted_systems'])}</dd>
    <dt>MTTR</dt><dd>{esc(report['mttr_minutes']) if report['mttr_minutes'] is not None else '<span class="pill warn">None</span>'} {'min' if report['mttr_minutes'] is not None else ''}</dd>
  </dl>

  <h3>Corroboration axes</h3>
  <table><tr><th></th><th>axis</th><th>strength</th><th>weight</th><th>source</th></tr>{''.join(rows)}</table>

  <h3>Root cause</h3><p class="text">{esc(report['root_cause'])}</p>
  <h3>Remediation</h3><p class="text">{esc(report['remediation'])}</p>
  <h3>Supporting evidence ({len(evidence)})</h3>{''.join(evidence)}
  <h3>Component nominees (relevance)</h3><ul class="nom">{nominees}</ul>
</section>"""


def render_page(overrides: dict) -> str:
    panels = []
    for name in INCIDENTS:
        default_query, _ = load_incident(name)
        panels.append(render_panel(name, overrides.get(name, default_query), default_query))
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Incident investigator</title>
<meta name="viewport" content="width=device-width,initial-scale=1"><style>{CSS}</style></head><body>
<header><h1>Production incident investigator</h1>
<p>Same code, two incidents. Confidence comes from how many independent document types agree — not from how relevant the top hit felt.</p></header>
<main>{''.join(panels)}</main></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        if url.path != "/":
            self.send_response(404)
            self.end_headers()
            return
        qs = parse_qs(url.query)
        overrides = {}
        if "incident" in qs and "q" in qs and qs["incident"][0] in INCIDENTS:
            overrides[qs["incident"][0]] = qs["q"][0]
        body = render_page(overrides).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # quieter console
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))


if __name__ == "__main__":
    import os
    port = int(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("PORT", PORT))
    print(f"viewer on http://localhost:{port}  (Ctrl+C to stop)")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
