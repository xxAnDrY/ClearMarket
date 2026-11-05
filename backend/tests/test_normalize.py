from datetime import datetime, timedelta, timezone

import pytest

from app.ingestion.dedupe import canonicalize_url, normalize_title, title_hash, url_hash
from app.ingestion.normalize import (
    RawArticle,
    classify,
    clean_text,
    extract_tickers,
    normalize,
    score_sentiment,
    truncate,
)

NOW = datetime(2026, 11, 5, 12, tzinfo=timezone.utc)


def build(**overrides):
    fields = {"title": "Markets open flat", "url": "https://example.com/a"} | overrides
    return normalize(RawArticle(**fields), source_id=1, default_category="macro", now=NOW)


@pytest.mark.parametrize("url", [
    "https://www.example.com/a/?utm_source=x&utm_medium=y",
    "https://example.com/a?fbclid=123#section",
    "http://EXAMPLE.com/a/",
])
def test_url_variants_share_one_hash(url):
    assert url_hash(canonicalize_url(url)) == url_hash(canonicalize_url("https://example.com/a"))


def test_meaningful_query_params_are_kept():
    first = canonicalize_url("https://example.com/news?id=1")
    second = canonicalize_url("https://example.com/news?id=2")
    assert first != second


def test_double_slash_path_from_ecb_feed_is_collapsed():
    url = "https://www.ecb.europa.eu//press/key/date/2026/html/x.en.html"
    assert canonicalize_url(url) == "https://www.ecb.europa.eu/press/key/date/2026/html/x.en.html"


def test_stored_url_keeps_www_and_trailing_slash():
    url = "https://www.example.com/story/?utm_source=x"
    assert canonicalize_url(url) == "https://www.example.com/story/"


def test_title_hash_ignores_case_accents_and_outlet_suffix():
    assert title_hash("Fed Holds Rates - Reuters") == title_hash("fed holds rates")
    assert normalize_title("Café: «prezzi» in calo!") == "cafe prezzi in calo"


def test_clean_text_strips_markup_and_scripts():
    assert clean_text("<p>Hello <b>world</b></p><script>alert(1)</script>") == "Hello world"
    assert clean_text("AT&amp;amp;T") == "AT&T"


def test_truncate_cuts_on_word_boundary():
    result = truncate("word " * 100, 20)
    assert result.endswith("…") and len(result) <= 21 and "wor…" not in result


@pytest.mark.parametrize("text,expected", [
    ("Nvidia and Apple lead gains", {"NVDA", "AAPL"}),
    ("Buying $TSLA today", {"TSLA"}),
    ("Shares of (NASDAQ: MSFT) rose", {"MSFT"}),
    ("Stock gained $100 on the day", set()),
    ("UniCredit raises guidance", {"UCG.MI"}),
    ("The trainee met senior staff", set()),   # "eni" dentro una parola non e' ENI
    ("AT&T subscriber numbers", set()),
])
def test_extract_tickers(text, expected):
    assert set(extract_tickers(text)) == expected


@pytest.mark.parametrize("text,tickers,expected", [
    ("Bitcoin tops 100k", [], "crypto"),
    ("Powell signals a pause", [], "monetary_policy"),
    ("US CPI cools in October", [], "macro"),
    ("Vanguard launches new ETF", [], "etf"),
    ("DAX closes higher", [], "stocks_eu"),
    ("UniCredit raises guidance", ["UCG.MI"], "stocks_eu"),
    ("Something unrelated", [], "macro"),
])
def test_classify(text, tickers, expected):
    assert classify(text, tickers, "macro") == expected


def test_locked_source_keeps_its_category():
    assert classify("Bitcoin mentioned in speech", [], "monetary_policy", lock_default=True) == "monetary_policy"


@pytest.mark.parametrize("title,label", [
    ("Apple shares surge after earnings beat", "positive"),
    ("Bank plunges on fraud probe", "negative"),
    ("Central bank publishes annual report", "neutral"),
    ("Shares fail to rally", "negative"),
])
def test_sentiment_labels(title, label):
    assert score_sentiment(title)[0] == label


def test_sentiment_score_is_bounded():
    assert -1 <= score_sentiment("crash crash crash fraud fraud bankruptcy")[1] <= 1


@pytest.mark.parametrize("url", ["javascript:alert(1)", "ftp://x/y", "", "intent://x"])
def test_unsafe_or_missing_urls_are_rejected(url):
    assert build(url=url) is None


def test_empty_title_is_rejected():
    assert build(title="  <p></p> ") is None


def test_future_date_is_clamped_to_now():
    assert build(published_at=NOW + timedelta(days=2)).published_at == NOW


def test_missing_date_defaults_to_now_and_naive_is_utc():
    assert build().published_at == NOW
    naive = build(published_at=datetime(2026, 11, 5, 9)).published_at
    assert naive == datetime(2026, 11, 5, 9, tzinfo=timezone.utc)


def test_summary_equal_to_title_is_dropped():
    assert build(summary="Markets open flat").summary == ""
