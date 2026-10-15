#!/usr/bin/env python3
"""Render docs/index.html from data/bonuses.json. No framework, no JavaScript needed.

    python build_site.py

docs/ is what GitHub Pages serves. The JSON is copied next to the page so it can be linked.
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent

CSS = """
:root{--bg:#f6f5f1;--card:#fff;--ink:#16181d;--muted:#5d6370;--line:#e3e1da;--accent:#0b6e4f;
--warn:#a35a00;--warn-bg:#fff4e0;--ok-bg:#e6f4ee;--chip:#f0efe9}
@media (prefers-color-scheme:dark){:root{--bg:#121417;--card:#1b1e23;--ink:#eceae4;--muted:#9aa0ab;
--line:#2c3038;--accent:#4cc39a;--warn:#f0b057;--warn-bg:#33270f;--ok-bg:#16302a;--chip:#252930}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:960px;margin:0 auto;padding:28px 16px 48px}
h1{font-size:1.6rem;line-height:1.2;margin:0 0 6px;letter-spacing:-.01em}
.sub{color:var(--muted);margin:0 0 22px}
.sub a{color:inherit}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden}
th,td{text-align:left;padding:14px 16px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:.78rem;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:600}
tbody tr:last-child td{border-bottom:0}
.casino{font-weight:650}
td:not(.casino) .flag{display:table;margin-top:6px}
.casino .flag{margin-left:1.6em}
.rank{display:inline-block;min-width:1.6em;color:var(--muted);font-weight:500}
.big{font-variant-numeric:tabular-nums;font-weight:650;font-size:1.05rem}
.sub2{display:block;color:var(--muted);font-size:.82rem}
a.src{color:var(--accent);font-weight:600;text-decoration:none}
a.src:hover{text-decoration:underline}
.flag{display:inline-block;white-space:nowrap;margin-top:4px;font-size:.75rem;padding:1px 8px;border-radius:99px;background:var(--warn-bg);color:var(--warn)}
.ok{background:var(--ok-bg);color:var(--accent)}
details{margin-top:8px;font-size:.85rem;color:var(--muted)}
summary{cursor:pointer;color:var(--accent)}
details p{margin:6px 0 0}
.meta{margin-top:22px;font-size:.85rem;color:var(--muted)}
.meta code{background:var(--chip);padding:1px 6px;border-radius:6px}
.rg{margin-top:14px;font-size:.8rem;color:var(--muted)}
@media (max-width:640px){
  table,thead,tbody,tr,td{display:block;width:100%}
  thead{display:none}
  table{border:0;background:none}
  tr{background:var(--card);border:1px solid var(--line);border-radius:12px;margin-bottom:14px;padding:6px 0}
  td{border:0;padding:8px 16px;display:grid;grid-template-columns:42% 58%;gap:8px}
  td::before{content:attr(data-label);color:var(--muted);font-size:.78rem;text-transform:uppercase;letter-spacing:.05em;padding-top:3px}
  td.casino{display:block;font-size:1.15rem;padding-top:12px}
  td.casino::before{content:none}
}
"""


def _cell_flag(status: str | None) -> str:
    if status == "unverified":
        return '<span class="flag" title="This value was not found word-for-word in the source text">check source</span>'
    if status == "missing":
        return '<span class="flag">not stated</span>'
    return ""


def _row(c: dict) -> str:
    d, checks = c.get("details", {}), c.get("checks", {})
    wager = d.get("wagering_display") or "—"
    applies = d.get("wagering_applies_to")
    applies_txt = f'<span class="sub2">on {escape(applies.replace("_", " "))}</span>' if applies and wager not in ("—", "None") else ""
    notes = f"<p><strong>Catch:</strong> {escape(d['notes'])}</p>" if d.get("notes") else ""
    status = ('<span class="flag">needs review</span>' if c.get("needs_review")
              else '<span class="flag ok">verified</span>')
    review = f' · <a class="src" href="{escape(d["review_url"])}">review</a>' if d.get("review_url") else ""
    return f"""<tr>
<td class="casino" data-label="Casino"><span class="rank">{c.get("rank", "")}.</span>{escape(c["casino"])}<br>{status}</td>
<td data-label="Welcome bonus"><div><span class="big">{escape(c.get("welcome_bonus") or "—")}</span>{_cell_flag(checks.get("welcome_bonus"))}
<details><summary>Terms as published</summary><p>{escape(c.get("raw_terms", ""))}</p>{notes}</details></div></td>
<td data-label="Wagering"><div><span class="big">{escape(wager)}</span>{applies_txt}{_cell_flag(checks.get("wagering_multiplier"))}</div></td>
<td data-label="Min deposit"><div><span class="big">{escape(c.get("minimum_deposit") or "—")}</span>{_cell_flag(checks.get("min_deposit_amount"))}</div></td>
<td data-label="Source"><div><a class="src" href="{escape(c["source_url"])}" rel="nofollow">source page</a>{review}</div></td>
</tr>"""


def render(data: dict) -> str:
    when = datetime.fromisoformat(data["generated_at"]).strftime("%d %b %Y, %H:%M UTC")
    rows = "\n".join(_row(c) for c in data["casinos"])
    src = data["source"]
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Casino Welcome Bonuses</title>
<meta name="description" content="Welcome bonus, wagering and minimum deposit for {len(data['casinos'])} online casinos, scraped from {escape(src['name'])}.">
<style>{CSS}</style></head>
<body><main>
<h1>Casino welcome bonuses</h1>
<p class="sub">Top {len(data['casinos'])} offers from <a href="{escape(src['url'])}" rel="nofollow">{escape(src['name'])}</a>, read by a language model and checked against the published terms. Updated {when}.</p>
<table>
<thead><tr><th>Casino</th><th>Welcome bonus</th><th>Wagering</th><th>Min deposit</th><th>Source</th></tr></thead>
<tbody>
{rows}
</tbody></table>
<p class="meta">Extracted with <code>{escape(data.get('extracted_with', ''))}</code>. Values marked “check source” were not found word-for-word in the casino's terms. <a class="src" href="bonuses.json">Raw JSON</a></p>
<p class="rg">18+ only. Offers change often; always read the casino's full terms. Gambling can be addictive. Online casino gambling is not legal in every country.</p>
</main></body></html>
"""


def build(json_path: Path, out_path: Path) -> None:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render(data), encoding="utf-8")
    target = out_path.parent / "bonuses.json"
    if target.resolve() != json_path.resolve():
        shutil.copyfile(json_path, target)
    (out_path.parent / ".nojekyll").touch()
    print(f"Built {out_path}")


if __name__ == "__main__":
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "bonuses.json"
    build(src, ROOT / "docs" / "index.html")
