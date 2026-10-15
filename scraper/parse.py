"""Turn the comparison page into one raw text block per casino.

This step is deliberately "dumb": it only finds where each casino's listing starts and ends
and keeps its text. Understanding the free-text terms is the language model's job (llm.py).
That split keeps the scraper resilient: if the site changes its wording, nothing here breaks.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

# Offer links on gambling.com go through /go/<country>/<casino-slug>/..., e.g.
#   UK: /go/uk/mr-vegas/offer/8458#listid=115&listtype=product-ranking-best&list_position=1...
#   IE: /go/ie/888/casino/play-now/103536#listid=150&listtype=primary&list_position=2...
OFFER_HREF = re.compile(r"/go/[a-z]{2}/(?P<slug>[a-z0-9-]+)/")
REVIEW_HREF = re.compile(r"/online-casinos/reviews/(?P<slug>[a-z0-9-]+)/?$")


@dataclass
class CasinoBlock:
    slug: str
    name: str
    position: int
    headline: str  # the bonus as advertised in the big link text, e.g. "100% up to £50 + 11 Free Spins"
    text: str  # everything in the listing: headline + small-print terms
    review_url: str | None


def _fragment_params(href: str) -> dict[str, str]:
    frag = urlsplit(href).fragment
    return {k: v[0] for k, v in parse_qs(frag).items()}


def _listing_container(anchor: Tag) -> Tag:
    """Climb from an offer link to the element that holds that one casino's listing."""
    li = anchor.find_parent("li")
    if li is not None:
        return li
    # Fallback for a layout without <li>: the highest ancestor that still contains just one casino.
    node = anchor
    while node.parent is not None and isinstance(node.parent, Tag):
        slugs = {
            m.group("slug")
            for a in node.parent.find_all("a", href=True)
            if (m := OFFER_HREF.search(a["href"]))
        }
        if len(slugs) > 1:
            break
        node = node.parent
    return node


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _casino_name(container: Tag, slug: str) -> str:
    img = container.find("img", alt=True) or container.find("img", title=True)
    if img is not None:
        name = (img.get("alt") or img.get("title") or "").strip()
        if name:
            return name
    return slug.replace("-", " ").title()


def extract_blocks(html: str, page_url: str) -> list[CasinoBlock]:
    """Return the casinos in the page's main ranked list, in ranked order."""
    soup = BeautifulSoup(html, "html.parser")
    for junk in soup(["script", "style", "noscript", "nav", "header", "footer"]):
        junk.decompose()

    found: dict[str, CasinoBlock] = {}
    main_list: str | None = None
    for anchor in soup.find_all("a", href=True):
        match = OFFER_HREF.search(anchor["href"])
        if not match:
            continue
        params = _fragment_params(anchor["href"])
        # The headline bonus is the link marked ctalocation=bonus-offer.
        if params.get("ctalocation") != "bonus-offer":
            continue
        # The main ranked list is the first one on the page. Country pages name it differently
        # (UK "product-ranking-best", IE "primary"), so we match on its list id, not its name.
        # That skips the later "best for..." and "also consider" lists.
        if main_list is None:
            main_list = params.get("listid", "")
        if params.get("listid", "") != main_list:
            continue
        slug = match.group("slug")
        if slug in found:
            continue
        container = _listing_container(anchor)
        review = container.find("a", href=REVIEW_HREF)
        review_url = urljoin(page_url, review["href"]) if review else None
        if review is not None:
            review.extract()  # "<Casino> Review" link text is navigation, not bonus terms
        found[slug] = CasinoBlock(
            slug=slug,
            name=_casino_name(container, slug),
            position=int(params.get("list_position", len(found) + 1)),
            headline=_clean(anchor.get_text(" ")),
            text=_clean(container.get_text(" ")),
            review_url=review_url,
        )

    return sorted(found.values(), key=lambda b: b.position)
