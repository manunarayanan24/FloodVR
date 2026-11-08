"""Render evals/results.json to a standalone HTML report."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from agents import settings

REPORT_PATH = settings.EVALS_DIR / "report.html"

_CSS = """
:root{--bg:#f7f7f5;--fg:#1a1a18;--muted:#6b6b66;--line:#dcdcd6;--card:#fff;
--ok:#1f7a4d;--bad:#b3261e;--warn:#9a6700;--accent:#2d5bd7}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#17171a;
--fg:#ececea;--muted:#9c9c96;--line:#32323a;--card:#1f1f24;--ok:#4ecb8d;
--bad:#ff6b5e;--warn:#e0a33a;--accent:#7fa0ff}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 ui-sans-serif,
system-ui,-apple-system,"Segoe UI",sans-serif;padding:32px 16px}
.wrap{max-width:980px;margin:0 auto}
h1{font-size:26px;margin:0 0 4px}h2{font-size:18px;margin:34px 0 10px}
.sub{color:var(--muted);margin:0 0 24px;font-size:14px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.card .n{font-size:28px;font-weight:650;letter-spacing:-.02em}
.card .l{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.05em}
.ok{color:var(--ok)}.bad{color:var(--bad)}.warn{color:var(--warn)}
table{width:100%;border-collapse:collapse;background:var(--card);
border:1px solid var(--line);border-radius:10px;overflow:hidden;font-size:14px}
th,td{text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);
vertical-align:top}th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;
color:var(--muted);font-weight:600}tr:last-child td{border-bottom:none}
code{font:13px/1.4 ui-monospace,"Cascadia Code",Consolas,monospace;
background:rgba(128,128,128,.14);padding:1px 5px;border-radius:4px}
.note{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--accent);
border-radius:8px;padding:12px 16px;margin:14px 0;font-size:14px}
.miss{color:var(--bad);font-weight:600}
"""


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


SET_LABELS = {
    "seed": "Seed set (ours)",
    "heldout": "Held-out #1 (now training)",
    "heldout2": "Held-out #2 (honest)",
}
SET_ORDER = ("seed", "heldout", "heldout2")


def _cards(results: dict[str, Any]) -> str:
    out = []
    for name in SET_ORDER:
        s = results["sets"].get(name)
        if not s:
            continue
        label = SET_LABELS[name]
        cls = "ok" if s["hijack_rate_guard_on"] <= 0.1 else (
            "warn" if s["hijack_rate_guard_on"] <= 0.4 else "bad")
        out.append(
            f'<div class="card"><div class="l">{label} &mdash; hijack, guard ON</div>'
            f'<div class="n {cls}">{_pct(s["hijack_rate_guard_on"])}</div>'
            f'<div class="l">{s["caught"]}/{s["total"]} caught &middot; '
            f'guard OFF 100%</div></div>'
        )
    clean = results.get("clean", {})
    if clean:
        cls = "ok" if clean["false_positive_rate"] <= 0.05 else "warn"
        out.append(
            f'<div class="card"><div class="l">False positives (clean)</div>'
            f'<div class="n {cls}">{_pct(clean["false_positive_rate"])}</div>'
            f'<div class="l">{clean["false_positives"]}/{clean["total"]} blocked</div></div>'
        )
    acc = results.get("claim_accuracy", {})
    if acc.get("checked"):
        cls = "ok" if acc["accuracy"] == 1 else "bad"
        out.append(
            f'<div class="card"><div class="l">Claim accuracy</div>'
            f'<div class="n {cls}">{_pct(acc["accuracy"])}</div>'
            f'<div class="l">{acc["correct"]}/{acc["checked"]} ground-truth checks</div></div>'
        )
    return f'<div class="cards">{"".join(out)}</div>'


def _technique_table(results: dict[str, Any]) -> str:
    rows = []
    techniques: set[str] = set()
    for s in results["sets"].values():
        techniques |= set(s["by_technique"])
    for tech in sorted(techniques):
        cells = []
        for name in SET_ORDER:
            s = results["sets"].get(name)
            t = (s or {}).get("by_technique", {}).get(tech)
            if not t:
                cells.append("<td>&mdash;</td>")
            else:
                cls = "ok" if t["recall"] == 1 else ("warn" if t["recall"] >= 0.5 else "miss")
                cells.append(
                    f'<td class="{cls}">{t["caught"]}/{t["total"]} '
                    f'({t["recall"] * 100:.0f}%)</td>'
                )
        rows.append(f"<tr><td><code>{html.escape(tech)}</code></td>{''.join(cells)}</tr>")
    return (
        "<table><tr><th>Technique</th><th>Seed</th><th>Held-out #1</th>"
        "<th>Held-out #2</th></tr>" + "".join(rows) + "</table>"
    )


def _missed_table(results: dict[str, Any]) -> str:
    rows = []
    for name in SET_ORDER:
        s = results["sets"].get(name)
        if not s:
            continue
        for m in s["missed_attacks"]:
            rows.append(
                f"<tr><td>{name}</td><td><code>{html.escape(m['id'])}</code></td>"
                f"<td><code>{html.escape(m['technique'])}</code></td>"
                f"<td>{html.escape(m['text'])}</td></tr>"
            )
    if not rows:
        return '<div class="note">No attack got through in this run.</div>'
    return (
        "<table><tr><th>Set</th><th>ID</th><th>Technique</th>"
        "<th>Attack that got through</th></tr>" + "".join(rows) + "</table>"
    )


def write_report(results: dict[str, Any], path: Path | None = None) -> Path:
    path = path or REPORT_PATH
    h1 = results["sets"].get("heldout")
    h2 = results["sets"].get("heldout2")
    parts = [
        "<p>Three sets, and only one of them is evidence.</p>",
        "<p><strong>Seed</strong> was written by the same person who wrote the "
        "rules, so its score is optimistic by construction.</p>",
    ]
    if h1:
        parts.append(
            "<p><strong>Held-out #1</strong> was written by Claude and first "
            "measured before any rule changed, at <strong>93.3% hijack</strong>. "
            "The rules were then rewritten by reading the attacks that defeated "
            f"them, which brought it to {_pct(h1['hijack_rate_guard_on'])} — but "
            "that act turned this set into a <em>training</em> set, and its score "
            "stopped being evidence.</p>"
        )
    if h2:
        parts.append(
            "<p><strong>Held-out #2</strong> was generated afterwards, against "
            "rules it had never seen. "
            f"<strong>{_pct(h2['hijack_rate_guard_on'])} of these still get "
            "through.</strong> That is the number we show judges. The distance "
            "between it and held-out #1 is how much of the tuning was real and "
            "how much was overfitting.</p>"
        )
    else:
        parts.append(
            "<p><strong>Held-out #2 has not been generated.</strong> Until it "
            "exists, every attack number here has been fitted to.</p>"
        )
    honesty = "".join(parts)

    body = f"""<div class="wrap">
<h1>FloodVR injection-guard evals</h1>
<p class="sub">{html.escape(results['generated_at'])} &middot;
layers: rules{' + NVIDIA guard model' if results['layers'].get('guard_model') else ' only'}
&middot; {'offline' if results.get('offline') else 'live'}</p>
{_cards(results)}
<div class="note">{honesty}</div>
<h2>Detection by technique</h2>
{_technique_table(results)}
<h2>Attacks that got through</h2>
{_missed_table(results)}
<h2>False positives on legitimate evidence</h2>
{_fp_table(results)}
<h2>Claim accuracy</h2>
{_accuracy_table(results)}
</div>"""

    doc = (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        "<title>FloodVR Guard Evals</title><style>" + _CSS + "</style></head><body>"
        + body + "</body></html>"
    )
    path.write_text(doc, encoding="utf-8")
    return path


def _fp_table(results: dict[str, Any]) -> str:
    clean = results.get("clean", {})
    flagged = clean.get("flagged", [])
    if not flagged:
        return ('<div class="note">Nothing legitimate was blocked, including the '
                'manifest note that genuinely says &ldquo;total loss&rdquo;.</div>')
    rows = "".join(
        f"<tr><td><code>{html.escape(f['id'])}</code></td>"
        f"<td><code>{html.escape(', '.join(f['rules']))}</code></td>"
        f"<td>{html.escape(f['text'])}</td></tr>" for f in flagged
    )
    return f"<table><tr><th>Document</th><th>Rule</th><th>Text</th></tr>{rows}</table>"


def _accuracy_table(results: dict[str, Any]) -> str:
    acc = results.get("claim_accuracy", {})
    if not acc.get("checks"):
        return '<div class="note">No accuracy checks ran.</div>'
    rows = "".join(
        f"<tr><td><code>{html.escape(c['item_id'])}</code></td>"
        f"<td>{html.escape(c['expected']['peril'])} / "
        f"{html.escape(c['expected']['coverage'])}</td>"
        f"<td class=\"{'ok' if c['ok'] else 'miss'}\">"
        f"{html.escape(c['got'].get('peril', '-'))} / "
        f"{html.escape(c['got'].get('coverage', '-'))}</td></tr>"
        for c in acc["checks"]
    )
    return (
        f"<table><tr><th>Item</th><th>Expected</th><th>Got</th></tr>{rows}</table>"
        f'<div class="note">Totals: ${acc["totals"]["low_usd"]:,.0f} &ndash; '
        f'${acc["totals"]["high_usd"]:,.0f} across {acc["line_items"]} line items, '
        f'{acc["priority_1_hazards"]} priority-1 hazards, '
        f'{acc["needs_human"]} flagged for human review.</div>'
    )


if __name__ == "__main__":
    data = json.loads((settings.EVALS_DIR / "results.json").read_text(encoding="utf-8"))
    print(write_report(data))
