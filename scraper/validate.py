"""Normalise the model's answer and check it against the source text.

Language models can state numbers that are not in the text. Every number the model returns
is checked against the casino's own listing text. Anything that can't be found there is
marked "unverified" and shown with a warning on the page instead of being silently trusted.
"""
from __future__ import annotations

import re
from typing import Any

SYMBOLS = {"£": "GBP", "€": "EUR", "$": "USD", "R": "ZAR"}
VALID_CURRENCIES = {"GBP", "EUR", "USD", "CAD", "AUD", "NZD", "ZAR", "SEK", "NOK", "DKK", "INR"}


def _num(value: Any) -> int | float | None:
    """Numbers come back as 10, 10.0, "10x" or "£10"; return 10 (an int when it's whole)."""
    if value is None or value == "" or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        n = float(value)
    else:
        match = re.search(r"\d+(?:[.,]\d+)?", str(value))
        if not match:
            return None
        n = float(match.group(0).replace(",", "."))
    return int(n) if n.is_integer() else n


def _fmt(n: float | None) -> str | None:
    if n is None:
        return None
    return str(int(n)) if n == int(n) else f"{n:g}"


def normalise(raw: dict[str, Any], page_currency: str | None) -> dict[str, Any]:
    currency = (raw.get("currency") or "").strip().upper() or None
    currency = SYMBOLS.get(currency, currency)
    if currency not in VALID_CURRENCIES:
        currency = page_currency
    return {
        "welcome_bonus": (raw.get("welcome_bonus") or "").strip() or None,
        "bonus_type": raw.get("bonus_type"),
        "wagering_multiplier": _num(raw.get("wagering_multiplier")),
        "wagering_applies_to": raw.get("wagering_applies_to"),
        "min_deposit_amount": _num(raw.get("min_deposit_amount")),
        "currency": currency,
        "notes": (raw.get("notes") or "").strip() or None,
    }


def _wagering_in_text(n: float, text: str) -> bool:
    t = text.lower()
    if n == 0:
        return bool(
            re.search(r"no wagering|0x|wagering:? none|winnings (?:are )?(?:paid as |are )?cash|cash spins", t)
        )
    num = re.escape(_fmt(n))
    return bool(
        re.search(rf"\b{num}\s*(?:x\b|×|times)", t)
        or re.search(rf"wager(?:ing)?(?: req\.?| requirement)?[^.]{{0,20}}\b{num}\b", t)
    )


def _deposit_in_text(n: float, text: str) -> bool:
    num = re.escape(_fmt(n))
    return bool(re.search(rf"[£€$]\s?{num}\b|\b{num}\s?(?:eur|gbp|usd)\b", text, re.IGNORECASE))


def detect_page_currency(text: str) -> str | None:
    counts = {code: text.count(sym) for sym, code in SYMBOLS.items() if sym != "R"}
    best = max(counts, key=counts.get)
    return best if counts[best] else None


def verify(fields: dict[str, Any], source_text: str) -> dict[str, str]:
    """Return a per-field status: verified / unverified / missing."""
    checks: dict[str, str] = {}

    checks["welcome_bonus"] = "verified" if fields["welcome_bonus"] else "missing"
    numbers = re.findall(r"\d+", fields["welcome_bonus"] or "")
    if numbers and not all(n in source_text for n in numbers):
        checks["welcome_bonus"] = "unverified"

    w = fields["wagering_multiplier"]
    checks["wagering_multiplier"] = (
        "missing" if w is None else "verified" if _wagering_in_text(w, source_text) else "unverified"
    )

    d = fields["min_deposit_amount"]
    checks["min_deposit_amount"] = (
        "missing" if d is None else "verified" if _deposit_in_text(d, source_text) else "unverified"
    )
    return checks


def display(fields: dict[str, Any]) -> dict[str, str | None]:
    """Human-readable strings, in the format the task's example uses."""
    cur = fields["currency"] or ""
    w = fields["wagering_multiplier"]
    d = fields["min_deposit_amount"]
    return {
        "welcome_bonus": fields["welcome_bonus"],
        "wagering_requirement": None if w is None else ("None" if w == 0 else f"{_fmt(w)}x"),
        "minimum_deposit": None if d is None else f"{_fmt(d)} {cur}".strip(),
    }
