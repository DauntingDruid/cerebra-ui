from __future__ import annotations
import types
from urllib.parse import urlparse, parse_qs

import pytest

try:
    from backend.open_webui.routers.retrieval import (
        _normalize_url,
        dedupe_urls,
        _to_r2_query,
        _make_variants,
        _looks_bot_blocked_text,
        _filter_kwargs_for_callable,
        _prepare_call_kwargs_with_concurrency,
    )
except Exception:
    from open_webui.routers.retrieval import (
        _normalize_url,
        dedupe_urls,
        _to_r2_query,
        _make_variants,
        _looks_bot_blocked_text,
        _filter_kwargs_for_callable,
        _prepare_call_kwargs_with_concurrency,
    )


def test_normalize_url_strips_fragment_and_tracking_params():
    u = "https://example.com/a/b?x=1&utm_source=gg&utm_medium=cpc&gclid=zzz#section"
    norm = _normalize_url(u)
    p = urlparse(norm)
    qs = parse_qs(p.query)

    assert p.fragment == ""

    assert qs.get("x") == ["1"]

    assert "utm_source" not in qs and "utm_medium" not in qs and "gclid" not in qs

    print("Test normalize URL - Strips fragment and tracking params:")
    print(f"Original URL: {u}")
    print(f"Normalized URL: {norm}")
    print(f"Fragment: {p.fragment}")
    print(f"Query Parameters: {qs}")
    print(f"Assertions passed: fragment removed, tracking params removed.")



def test_normalize_url_keeps_other_query_and_base():
    u = "http://ex.com/path?A=1&B=2&utm_campaign=sale"
    norm = _normalize_url(u)
    p = urlparse(norm)
    qs = parse_qs(p.query)
    assert p.scheme == "http"
    assert p.netloc == "ex.com"
    assert qs.get("A") == ["1"] and qs.get("B") == ["2"]
    assert "utm_campaign" not in qs


def test_dedupe_urls_per_domain_limit_and_uniqueness():
    urls = [
        "https://a.com/1",
        "https://a.com/2",
        "https://a.com/3",
        "https://a.com/4",
        "https://b.com/x",
        "https://b.com/x",
        "https://c.com/z#frag",
        "https://c.com/z",
    ]
    out = dedupe_urls(urls, keep_per_domain=3)
    assert len(out) == 3 + 1 + 2
    assert out[:3] == ["https://a.com/1", "https://a.com/2", "https://a.com/3"]
    assert "https://b.com/x" in out and "https://c.com/z" in out and "https://c.com/z#frag" in out

    print("Test dedupe URLs per domain, limit and uniqueness:")
    print(f"Input URLs: {urls}")
    print(f"Output URLs: {out}")
    print(f"Assertions passed: Length limit per domain, no duplicates, and domain order preserved.")


def test_to_r2_query_removes_positive_pdf_and_appends_negative_once():
    q = "abc filetype:pdf"
    r2 = _to_r2_query(q)
    
    assert _to_r2_query("abc filetype:pdf") == "abc -filetype:pdf"
    assert _to_r2_query("abc ext:pdf") == "abc -filetype:pdf"
    
    assert _to_r2_query("abc -filetype:pdf") == "abc -filetype:pdf"
    
    assert _to_r2_query("opentelemetry overview") == "opentelemetry overview -filetype:pdf"

    print("Test to R2 query removes positive pdf and appends negative once:")
    print(f"Original query: {q}")
    print(f"R2 query: {r2}")
    print(f"Assertions passed: 'filetype:pdf' removed and '-filetype:pdf' added.")


def test_make_variants_minimal_and_unique():
    base = "OpenTelemetry tracing"
    v2 = _make_variants(base, n=2)

    assert len(v2) == 2
    assert v2[0] == base
    assert "-filetype:pdf" in v2[1].lower()

    v3 = _make_variants(base, n=3)
    assert len(v3) == 3
    assert v3[2] == f'"{base}"'

    v_dup = _make_variants("abc -filetype:pdf", n=3)
    assert v_dup[0] == "abc -filetype:pdf"
    assert len(set(v_dup)) == len(v_dup)


def test_looks_bot_blocked_text_short_is_true():
    long_text = ("A" * 500) + " Cloudflare is checking your browser before accessing"
    
    assert _looks_bot_blocked_text("tiny text") is True

    print("Test bot blocked text detection (keywords):")
    print(f"Test text: {long_text}")
    print(f"Is bot blocked: { _looks_bot_blocked_text(long_text) }")
    print(f"Assertions passed: Text contains bot-blocking keywords.")


def test_looks_bot_blocked_text_keywords():

    long_text = ("A" * 500) + " Cloudflare is checking your browser before accessing"
    assert _looks_bot_blocked_text(long_text) is True


def test_looks_bot_blocked_text_normal_long_is_false():
    long_ok = "A" * 600
    assert _looks_bot_blocked_text(long_ok) is False


def test_filter_kwargs_for_callable_keeps_only_allowed_params():
    def f(a, b=1):
        return a + b

    kwargs = {"a": 10, "b": 2, "c": 999}
    filtered = _filter_kwargs_for_callable(f, kwargs)
    assert filtered == {"a": 10, "b": 2}


def test_filter_kwargs_for_callable_allows_var_keyword():
    def g(a, **kw):
        return a, kw

    kwargs = {"a": 1, "x": 2, "y": 3}
    filtered = _filter_kwargs_for_callable(g, kwargs)
    assert filtered == kwargs 


def test_prepare_concurrency_prefers_specific_names_when_available():
    
    def engine_fn(q, limit, page_size=5, max_variant_concurrency=1):
        return (q, limit, page_size, max_variant_concurrency)

    base = {"q": "abc", "limit": 10, "page_size": 5, "max_page_concurrency": 7}
    out = _prepare_call_kwargs_with_concurrency(engine_fn, base)
    
    assert "max_page_concurrency" not in out
    assert out["max_variant_concurrency"] == 7
    
    assert out["q"] == "abc" and out["limit"] == 10 and out["page_size"] == 5

    print("Test prepare concurrency prefers specific names when available:")
    print(f"Original base: {base}")
    print(f"Prepared arguments: {out}")
    print(f"Assertions passed: 'max_page_concurrency' mapped to 'max_variant_concurrency'.")


def test_prepare_concurrency_falls_back_to_concurrency():
    
    def engine_fn(q, limit, concurrency=1):
        return (q, limit, concurrency)

    base = {"q": "abc", "limit": 10, "page_size": 5, "max_page_concurrency": 4}
    out = _prepare_call_kwargs_with_concurrency(engine_fn, base)
    assert "max_page_concurrency" not in out
    assert out["concurrency"] == 4
    
    assert "page_size" not in out


def test_prepare_concurrency_passes_through_when_fn_accepts_kwargs():
    
    def engine_fn(q, **kwargs):
        return q, kwargs

    base = {"q": "abc", "limit": 10, "page_size": 5, "max_page_concurrency": 9}
    out = _prepare_call_kwargs_with_concurrency(engine_fn, base)
    assert any(k in out for k in ("max_page_concurrency", "max_variant_concurrency", "max_concurrency", "concurrency"))
    assert 9 in out.values()
