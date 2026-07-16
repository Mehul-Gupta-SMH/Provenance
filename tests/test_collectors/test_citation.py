"""Tests for provenance/collectors/citation.py (PLAN.md section 14, Collectors 7-8)."""
from __future__ import annotations

from provenance.collectors.citation import CitationExtractor


def test_citation_extractor_urls_dedupe_and_trailing_punctuation(test_settings):
    extractor = CitationExtractor(test_settings)
    raw_response = (
        "Check the docs at https://docs.acme.com/guide. "
        "Also see https://blog.acme.com/post, and again https://docs.acme.com/guide "
        "for reference."
    )

    results = extractor.collect(raw_response, "Acme")

    urls = [r.cited_url for r in results]
    assert urls == ["https://docs.acme.com/guide", "https://blog.acme.com/post"]
    assert all(not u.endswith(".") and not u.endswith(",") for u in urls)


def test_citation_extractor_content_type_classification(test_settings):
    extractor = CitationExtractor(test_settings)
    raw_response = (
        "https://docs.acme.com/reference "
        "https://blog.acme.com/post "
        "https://acme.com/vs-competitor "
        "https://acme.com/review "
        "https://reddit.com/r/acme "
        "https://acme.com/random-page"
    )

    results = extractor.collect(raw_response, "Acme")
    by_url = {r.cited_url: r.content_type for r in results}

    assert by_url["https://docs.acme.com/reference"] == "docs"
    assert by_url["https://blog.acme.com/post"] == "blog"
    assert by_url["https://acme.com/vs-competitor"] == "comparison"
    assert by_url["https://acme.com/review"] == "review"
    assert by_url["https://reddit.com/r/acme"] == "forum"
    assert by_url["https://acme.com/random-page"] is None


def test_citation_extractor_www_prefix_stripped_from_domain(test_settings):
    extractor = CitationExtractor(test_settings)

    results = extractor.collect("See https://www.acme.com/docs for details.", "Acme")

    assert results[0].domain == "acme.com"


def test_citation_extractor_no_urls_returns_empty_list(test_settings):
    extractor = CitationExtractor(test_settings)

    assert extractor.collect("No links here at all.", "Acme") == []
    assert extractor.collect("", "Acme") == []
