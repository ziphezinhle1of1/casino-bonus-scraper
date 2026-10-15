"""Language-model step: free-text bonus terms -> structured fields.

Works with any OpenAI-compatible API (Google Gemini, Groq, OpenAI, OpenRouter, ...) or
Anthropic's API. Only `requests` is needed, so there is no SDK lock-in.

Pick a provider with environment variables (see README):
    LLM_PROVIDER = gemini | groq | openai | anthropic   (default: gemini, it has a free tier)
    LLM_API_KEY  = your key
    LLM_MODEL    = optional, overrides the provider's default model
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Callable

import requests

PROVIDERS: dict[str, dict[str, str]] = {
    # Model names change over time. If a default stops working, set LLM_MODEL to a current one
    # from the provider's model list.
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-3.8-flash",  # 2.5-flash was retired for new users (found on first real run)
    },
    # llama-3.3-70b-versatile was shut down 16 Aug 2026; this is Groq's recommended replacement.
    "groq": {"base_url": "https://api.groq.com/openai/v1", "model": "openai/gpt-oss-120b"},
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
    "anthropic": {"base_url": "https://api.anthropic.com/v1", "model": "claude-haiku-5-5"},
}

SYSTEM_PROMPT = """You extract online casino welcome-bonus terms into strict JSON.
Use ONLY facts stated in the text. Never guess. If a value is not stated, use null.

Return exactly this JSON object:
{
  "welcome_bonus": string,            // short, e.g. "100% up to £50 + 11 Free Spins"
  "bonus_type": "deposit_match" | "free_spins" | "cashback" | "bonus_funds" | "other",
  "wagering_multiplier": number|null, // e.g. 10 for "10x". 0 if the text says "no wagering".
  "wagering_applies_to": "bonus" | "deposit" | "deposit_and_bonus" | "free_spin_winnings" | null,
  "min_deposit_amount": number|null,  // the minimum deposit to qualify, e.g. 10
  "currency": string|null,            // ISO code: GBP, EUR, USD ...
  "notes": string|null                // one short line on any important catch (max bet, expiry, excluded payment methods)
}

Rules:
- "Wager req. 10x" or "wager ... 10 times" means wagering_multiplier = 10.
- If the only requirement is to stake an amount to unlock the offer (e.g. "Bet £10, get 50 free spins") and
  winnings have no wagering, wagering_multiplier = 0. If wagering is mentioned without a number, use null.
- "Min dep £20" or "deposit £25 to get" gives min_deposit_amount. A required stake is not a deposit,
  unless the text also says to deposit it ("Dep & spend min £10" means deposit 10).
- Output JSON only, no commentary."""

LLMCaller = Callable[[str, str], str]  # (system_prompt, user_text) -> raw model text


def _config() -> tuple[str, str, str, str]:
    provider = os.environ.get("LLM_PROVIDER", "gemini").lower()
    if provider not in PROVIDERS:
        raise SystemExit(f"Unknown LLM_PROVIDER '{provider}'. Use one of: {', '.join(PROVIDERS)}")
    key = os.environ.get("LLM_API_KEY") or ""
    if not key:
        raise SystemExit("Set LLM_API_KEY (see README: 'Get a free API key').")
    model = (os.environ.get("LLM_MODEL") or "").strip() or PROVIDERS[provider]["model"]
    if model.lower() in PROVIDERS:
        raise SystemExit(
            f"LLM_MODEL is set to '{model}', which is a provider name, not a model. "
            f"Put it in LLM_PROVIDER instead and delete the LLM_MODEL line from .env."
        )
    return provider, PROVIDERS[provider]["base_url"], model, key


RETRYABLE = (429, 500, 502, 503, 504, 529)


def _post_with_retry(url: str, headers: dict, payload: dict, retries: int = 6) -> dict:
    """Free tiers are often busy (503), rate-limited (429) or slow (timeouts). Wait and retry
    those with growing gaps: 5, 10, 20, 40, 60s (about 2 minutes in total). Anything else,
    like a wrong key (401) or a retired model (404), fails at once because retrying won't help."""
    problem = ""
    for attempt in range(retries):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=(10, 90))
        except (requests.Timeout, requests.ConnectionError) as exc:
            problem = f"no answer ({type(exc).__name__})"
        else:
            if resp.ok:
                return resp.json()
            if resp.status_code not in RETRYABLE:
                raise RuntimeError(f"LLM API error {resp.status_code}: {resp.text[:300]}")
            problem = f"busy (HTTP {resp.status_code})"
        if attempt < retries - 1:
            wait = min(60, 5 * 2 ** attempt)
            print(f"     model {problem}, retrying in {wait}s ({attempt + 1}/{retries - 1})...")
            time.sleep(wait)
    raise RuntimeError(
        f"LLM API still {problem} after {retries} tries. The provider is overloaded; "
        "try again later, or switch LLM_PROVIDER (see README)."
    )


def make_caller() -> tuple[LLMCaller, str]:
    """Build the real API caller from env vars. Returns (caller, 'provider/model')."""
    provider, base_url, model, key = _config()

    if provider == "anthropic":
        def call(system: str, text: str) -> str:
            data = _post_with_retry(
                f"{base_url}/messages",
                {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                {
                    "model": model,
                    "max_tokens": 600,
                    "temperature": 0,
                    "system": system,
                    "messages": [{"role": "user", "content": text}],
                },
            )
            return "".join(b.get("text", "") for b in data.get("content", []))
    else:
        def call(system: str, text: str) -> str:
            data = _post_with_retry(
                f"{base_url}/chat/completions",
                {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                {
                    "model": model,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": text},
                    ],
                },
            )
            return data["choices"][0]["message"]["content"]

    return call, f"{provider}/{model}"


def parse_json(raw: str) -> dict[str, Any]:
    """Models sometimes wrap JSON in ```json fences or add a sentence; tolerate that."""
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object in model output: {raw[:200]!r}")
    return json.loads(match.group(0))


def extract_terms(call: LLMCaller, casino_name: str, block_text: str) -> dict[str, Any]:
    user = f"Casino: {casino_name}\n\nListing text (headline and terms):\n{block_text}"
    try:
        return parse_json(call(SYSTEM_PROMPT, user))
    except (ValueError, json.JSONDecodeError):
        # One retry with a firmer reminder; models occasionally drift from the format.
        return parse_json(call(SYSTEM_PROMPT, user + "\n\nReturn ONLY the JSON object."))