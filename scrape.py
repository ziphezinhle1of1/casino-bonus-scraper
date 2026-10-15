#!/usr/bin/env python3
"""Scrape casino welcome bonuses, structure them with a language model, write JSON, build the page.

    python scrape.py                 # the single command: scrape 3 casinos -> data/bonuses.json -> docs/index.html

Options:
    --limit N      number of casinos (default 3)
    --url URL      a different gambling.com bonus page (e.g. the Ireland one, which lists EUR)
    --html FILE    parse a saved copy of the page instead of downloading it (debugging)
    --no-site      skip rebuilding docs/index.html
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from scraper import fetch, llm, parse, validate

ROOT = Path(__file__).resolve().parent
DEFAULT_URL = "https://www.gambling.com/uk/online-casinos/bonus"
DEFAULT_OUT = ROOT / "data" / "bonuses.json"


def build_record(block: parse.CasinoBlock, call: llm.LLMCaller, page_url: str, page_currency: str | None) -> dict:
    raw = llm.extract_terms(call, block.name, block.text)
    fields = validate.normalise(raw, page_currency)
    checks = validate.verify(fields, block.text)
    shown = validate.display(fields)
    return {
        "rank": block.position,
        "casino": block.name,
        # The four fields the task asks for:
        "welcome_bonus": shown["welcome_bonus"] or block.headline,
        "wagering_requirement": fields["wagering_multiplier"],
        "minimum_deposit": shown["minimum_deposit"],
        "source_url": page_url,
        # Extra detail, kept so every value can be traced and checked:
        "details": {
            "wagering_display": shown["wagering_requirement"],
            "wagering_applies_to": fields["wagering_applies_to"],
            "min_deposit_amount": fields["min_deposit_amount"],
            "currency": fields["currency"],
            "bonus_type": fields["bonus_type"],
            "notes": fields["notes"],
            "advertised_headline": block.headline,
            "review_url": block.review_url,
        },
        "checks": checks,
        "needs_review": any(v != "verified" for v in checks.values()),
        "raw_terms": block.text,
    }


def write_atomic(path: Path, data: dict) -> None:
    """Write to a temp file then rename, so a crash never leaves a half-written JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def run(url: str, limit: int, html_file: str | None, out: Path, call: llm.LLMCaller, model_label: str) -> dict:
    if html_file:
        html = Path(html_file).read_text(encoding="utf-8")
        print(f"Parsing saved page {html_file}")
    else:
        print(f"Checking robots.txt and fetching {url}")
        html = fetch.fetch_html(url)

    blocks = parse.extract_blocks(html, url)
    if not blocks:
        raise RuntimeError("Found no casino listings on the page. The layout may have changed.")
    blocks = blocks[:limit]
    page_currency = validate.detect_page_currency(" ".join(b.text for b in blocks))

    casinos = []
    for block in blocks:
        print(f"  #{block.position} {block.name}: asking {model_label} to read the terms")
        record = build_record(block, call, url, page_currency)
        flag = "  (needs review)" if record["needs_review"] else ""
        print(f"     -> {record['welcome_bonus']} | wagering {record['wagering_requirement']} "
              f"| min deposit {record['minimum_deposit']}{flag}")
        casinos.append(record)

    data = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {"name": "Gambling.com", "url": url},
        "extracted_with": model_label,
        "casino_count": len(casinos),
        "casinos": casinos,
    }
    write_atomic(out, data)
    print(f"Wrote {len(casinos)} casinos to {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")
    if len(casinos) < limit:
        print(f"Warning: asked for {limit} casinos but the page only had {len(casinos)}.", file=sys.stderr)
    return data


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Read KEY=value lines from .env without needing an extra package. Real env vars win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split(" #", 1)[0].strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> int:
    load_dotenv()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--limit", type=int, default=3)
    ap.add_argument("--html", help="parse a saved HTML file instead of fetching")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--no-site", action="store_true")
    args = ap.parse_args()

    try:
        call, label = llm.make_caller()
        run(args.url, args.limit, args.html, args.out, call, label)
    except fetch.BlockedError as exc:
        print(f"Blocked: {exc}\nThe task rule applies: switch to another source (--url).", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - top-level: report clearly, keep the last good JSON
        print(f"Scrape failed: {exc}\nThe previous data/bonuses.json was left untouched.", file=sys.stderr)
        return 1

    if not args.no_site:
        from build_site import build
        build(args.out, ROOT / "docs" / "index.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
