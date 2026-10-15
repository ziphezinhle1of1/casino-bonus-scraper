"""Tests run fully offline: a saved page fixture and a fake language model stand in for the network."""
import json
from pathlib import Path

import pytest

import build_site
import scrape
from scraper import llm, parse, validate

FIXTURE = Path(__file__).parent / "fixtures" / "gambling_com_sample.html"
URL = "https://www.gambling.com/uk/online-casinos/bonus"

FAKE_ANSWERS = {
    "Mr Vegas Casino": {"welcome_bonus": "100% up to £50 + 11 Free Spins", "bonus_type": "deposit_match",
                        "wagering_multiplier": 10, "wagering_applies_to": "deposit",
                        "min_deposit_amount": 10, "currency": "GBP", "notes": "60 days to wager"},
    "Mega Riches Casino": {"welcome_bonus": "100% up to £25 + 50 Millionaire chances", "bonus_type": "deposit_match",
                           "wagering_multiplier": "10x", "wagering_applies_to": "bonus",
                           "min_deposit_amount": "£10", "currency": "£", "notes": None},
    # Deliberately wrong: 35x and £20 appear nowhere in the Videoslots terms.
    "Videoslots Casino": {"welcome_bonus": "100% up to £50 + 11 Free Spins", "bonus_type": "deposit_match",
                          "wagering_multiplier": 35, "wagering_applies_to": "bonus",
                          "min_deposit_amount": 20, "currency": "GBP", "notes": None},
}


def fake_llm(system: str, text: str) -> str:
    name = text.split("\n", 1)[0].removeprefix("Casino: ").strip()
    return "```json\n" + json.dumps(FAKE_ANSWERS[name]) + "\n```"


def blocks():
    return parse.extract_blocks(FIXTURE.read_text(encoding="utf-8"), URL)


def test_finds_ranked_list_only_in_order():
    found = blocks()
    assert [b.slug for b in found] == ["mr-vegas", "mega-riches", "videoslots", "peachy-games"]
    assert found[0].name == "Mr Vegas Casino"
    assert "minimum initial deposit of £10" in found[0].text
    assert found[0].review_url.endswith("/reviews/mr-vegas")
    assert "Review" not in found[0].text
    assert all("betmgm" not in b.slug for b in found)  # secondary list ignored


def test_scripts_and_nav_are_not_in_block_text():
    assert all("£999" not in b.text and "32Red" not in b.text for b in blocks())


def test_llm_json_tolerates_code_fences():
    assert llm.parse_json('Sure!\n```json\n{"a": 1}\n```') == {"a": 1}


def test_normalise_cleans_strings_and_symbols():
    f = validate.normalise(FAKE_ANSWERS["Mega Riches Casino"], "GBP")
    assert f["wagering_multiplier"] == 10 and f["min_deposit_amount"] == 10 and f["currency"] == "GBP"


@pytest.mark.parametrize("text,n,expected", [
    ("Wager req. 10x.", 10, True),
    ("wager an amount equal to 10 times the value", 10, True),
    ("Wager req. 10x.", 35, False),
    ("No wagering on Free Spins; winnings paid as cash.", 0, True),
])
def test_wagering_grounding(text, n, expected):
    assert validate._wagering_in_text(n, text) is expected


def test_hallucinated_values_are_flagged(tmp_path):
    out = tmp_path / "bonuses.json"
    data = scrape.run(URL, 3, str(FIXTURE), out, fake_llm, "fake/model")
    by_name = {c["casino"]: c for c in data["casinos"]}

    assert by_name["Mr Vegas Casino"]["needs_review"] is False
    assert by_name["Mega Riches Casino"]["minimum_deposit"] == "10 GBP"
    vs = by_name["Videoslots Casino"]
    assert vs["needs_review"] is True
    assert vs["checks"]["wagering_multiplier"] == "unverified"
    assert vs["checks"]["min_deposit_amount"] == "unverified"


def test_output_has_the_four_required_fields(tmp_path):
    out = tmp_path / "bonuses.json"
    scrape.run(URL, 3, str(FIXTURE), out, fake_llm, "fake/model")
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["casino_count"] == 3
    for c in data["casinos"]:
        for key in ("welcome_bonus", "wagering_requirement", "minimum_deposit", "source_url"):
            assert key in c
        assert c["source_url"] == URL


def test_failed_run_keeps_previous_json(tmp_path):
    out = tmp_path / "bonuses.json"
    out.write_text('{"keep": true}', encoding="utf-8")
    empty = tmp_path / "empty.html"
    empty.write_text("<html><body>nothing</body></html>", encoding="utf-8")
    with pytest.raises(RuntimeError):
        scrape.run(URL, 3, str(empty), out, fake_llm, "fake/model")
    assert json.loads(out.read_text(encoding="utf-8")) == {"keep": True}


def test_page_renders_and_escapes(tmp_path):
    out = tmp_path / "bonuses.json"
    scrape.run(URL, 3, str(FIXTURE), out, fake_llm, "fake/model")
    page = tmp_path / "site" / "index.html"
    build_site.build(out, page)
    html = page.read_text(encoding="utf-8")
    assert 'name="viewport"' in html
    assert html.count("<tr>") == 4  # header + 3 casinos
    assert "check source" in html  # the flagged Videoslots values
    assert (tmp_path / "site" / "bonuses.json").exists()


def test_irish_page_layout_is_parsed():
    html = (Path(__file__).parent / "fixtures" / "gambling_com_ie_sample.html").read_text(encoding="utf-8")
    found = parse.extract_blocks(html, "https://www.gambling.com/ie/online-casinos/bonus")
    assert [b.slug for b in found] == ["lottoland", "888"]  # secondary list skipped
    assert found[0].name == "Lottoland Casino"
    assert validate.detect_page_currency(" ".join(b.text for b in found)) == "EUR"
