"""Polite HTTP fetching: robots.txt check, honest User-Agent, retries, no block-bypassing."""
from __future__ import annotations

import time
import urllib.robotparser
from urllib.parse import urlsplit

import requests

USER_AGENT = "CasinoBonusScraper/1.0 (screening task; respects robots.txt)"
TIMEOUT = 20


class BlockedError(RuntimeError):
    """Raised when robots.txt disallows us or the site blocks the request.

    We never try to get around this. The task rule is: if a source blocks you, switch source.
    """


def robots_allows(url: str, user_agent: str = USER_AGENT) -> bool:
    parts = urlsplit(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    resp = requests.get(robots_url, headers={"User-Agent": user_agent}, timeout=TIMEOUT)
    if resp.status_code in (401, 403):
        return False  # robots.txt itself is locked: treat the whole site as off-limits
    if resp.status_code >= 400:
        return True  # no robots.txt means no restrictions (RFC 9309)
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(resp.text.splitlines())
    return parser.can_fetch(user_agent, url)


def fetch_html(url: str, retries: int = 3) -> str:
    if not robots_allows(url):
        raise BlockedError(f"robots.txt disallows {url} for our user agent")

    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
        except requests.RequestException as exc:
            last_error = exc
        else:
            if resp.status_code in (401, 403, 429) or "captcha" in resp.text[:5000].lower():
                raise BlockedError(
                    f"{url} answered {resp.status_code} or showed a CAPTCHA; not bypassing it"
                )
            if resp.ok:
                return resp.text
            last_error = RuntimeError(f"HTTP {resp.status_code} from {url}")
        time.sleep(2 ** attempt)
    raise RuntimeError(f"Could not fetch {url} after {retries} tries: {last_error}")
