# Casino bonus scraper

Pulls the welcome bonus, wagering requirement and minimum deposit for 3 online casinos from
[Gambling.com's UK bonus comparison page](https://www.gambling.com/uk/online-casinos/bonus).
A language model turns each casino's free-text terms into structured fields, and the result
is written to `data/bonuses.json` and published as a phone-friendly page.

**Live page:** https://YOUR-GITHUB-USERNAME.github.io/casino-bonus-scraper/

## How it works

```
gambling.com page ──► robots.txt check ──► split page into one block per casino   (scraper/fetch.py, parse.py)
                                                   │
                                                   ▼
                            language model reads each block's terms → JSON        (scraper/llm.py)
                                                   │
                                                   ▼
             every number checked against the source text; unmatched = flagged    (scraper/validate.py)
                                                   │
                                                   ▼
                      data/bonuses.json ──► docs/index.html (GitHub Pages)        (build_site.py)
```

Design choices:

- **The HTML parser only finds where each casino's listing starts and ends.** It never
  tries to read the terms with regexes. Understanding "wager an amount equal to 10 times your
  first deposit" is the model's job. This keeps the scraper working when the site rewords its offers.
- **The model's answers are checked, not trusted.** Each number the model returns must appear
  in that casino's own text. If it doesn't, the record gets `"needs_review": true` and the page
  shows "check source" next to that value.
- **Traceable output.** Each record keeps the raw terms text, the model used, and a per-field
  check status, so any value can be traced back to where it came from.
- **Safe failure.** If a run fails, the previous `bonuses.json` is left untouched (atomic write).
- **Polite.** Checks robots.txt, sends an honest User-Agent, backs off on errors, and stops
  (instead of working around it) on 403, 429 or a CAPTCHA.

## Install and run

Needs Python 3.10+.

```bash
git clone https://github.com/YOUR-GITHUB-USERNAME/casino-bonus-scraper.git
cd casino-bonus-scraper
pip install -r requirements.txt
cp .env.example .env        # then paste your API key into .env
python scrape.py            # the single command: scrape -> data/bonuses.json -> docs/index.html
```

### Get a free API key

Any of these works; set `LLM_PROVIDER` to match.

| Provider | `LLM_PROVIDER` | Key from |
|---|---|---|
| Google Gemini (free tier) | `gemini` | https://aistudio.google.com/apikey |
| Groq (free tier) | `groq` | https://console.groq.com/keys |
| OpenAI | `openai` | https://platform.openai.com/api-keys |
| Anthropic | `anthropic` | https://console.anthropic.com/ |

Model names change over time. If the default model for your provider is retired, set
`LLM_MODEL` in `.env` to a current one from that provider's model list.

### Options

```bash
python scrape.py --limit 5                                         # more casinos
python scrape.py --url https://www.gambling.com/ie/online-casinos/bonus   # Irish page, prices in EUR
python scrape.py --html saved_page.html                            # parse a saved copy (debugging)
python build_site.py                                               # rebuild the page only
python -m pytest                                                   # tests (offline: fixture + fake model)
```

## Publish the page (GitHub Pages)

1. Push this repo to GitHub (public).
2. **Settings → Pages → Build and deployment:** Source = *Deploy from a branch*, Branch = `main`, folder = `/docs`.
3. The page appears at `https://YOUR-GITHUB-USERNAME.github.io/casino-bonus-scraper/` within a minute or two.

### Optional: daily update

`.github/workflows/daily.yml` re-scrapes every day and commits the new JSON and page.
Add a repository secret `LLM_API_KEY` and a variable `LLM_PROVIDER`. If a run fails,
GitHub emails you. Note: some sites block cloud server addresses; if the Actions run
gets a 403, the scraper stops (as the rules require) and you can keep running it locally.

## Output format

```json
{
  "generated_at": "2026-10-14T10:23:00+00:00",
  "source": { "name": "Gambling.com", "url": "https://www.gambling.com/uk/online-casinos/bonus" },
  "extracted_with": "gemini/gemini-2.5-flash",
  "casinos": [
    {
      "rank": 1,
      "casino": "…",
      "welcome_bonus": "100% up to £50 + 11 Free Spins",
      "wagering_requirement": 10,
      "minimum_deposit": "10 GBP",
      "source_url": "https://www.gambling.com/uk/online-casinos/bonus",
      "details": { "wagering_applies_to": "deposit", "currency": "GBP", "notes": "…", "review_url": "…" },
      "checks": { "welcome_bonus": "verified", "wagering_multiplier": "verified", "min_deposit_amount": "verified" },
      "needs_review": false,
      "raw_terms": "…the casino's terms as published…"
    }
  ]
}
```

`wagering_requirement` is the multiplier (10 means 10x). `0` means no wagering; `null` means
the terms don't say.

## What's missing / next steps

- One source only. For production, each extra source gets its own small "find the listings"
  parser; the model step and checks are shared.
- Values flagged "needs review" are shown with a warning, not fixed automatically.
- No history yet: each run replaces the last. A database table keyed by casino and date would
  allow tracking changes over time (see the production write-up).

## Project layout

```
scrape.py            entry point (single command)
build_site.py        JSON -> docs/index.html
scraper/fetch.py     robots.txt, polite fetching
scraper/parse.py     page -> one text block per casino
scraper/llm.py       model call (any OpenAI-compatible API or Anthropic)
scraper/validate.py  normalise + check every value against the source text
tests/               offline tests with a saved page and a fake model
data/bonuses.json    output
docs/                the published page
```
