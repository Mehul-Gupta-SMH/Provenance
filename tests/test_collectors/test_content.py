"""Tests for provenance/collectors/content.py (content/citability collector)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from provenance.collectors.content import ContentCollector

_CANNED_HTML = """
<html>
<head>
<title>Acme Graph Database Docs</title>
<script type="application/ld+json">
{"@context": "https://schema.org", "@type": "FAQPage", "name": "FAQ"}
</script>
</head>
<body>
<h1>Acme Graph Database</h1>
<h2>Why 42% faster</h2>
<p>Acme handles 1000000 queries per second, a 42% improvement over last year.
We serve 99.9 percent uptime for our 500 customers.</p>
<ul><li>Fast</li><li>Reliable</li></ul>
<ol><li>Step one</li></ol>
<table><tr><td>Row</td></tr></table>
<a href="https://acme.example.com/about">About</a>
<a href="https://other-host.example.com/blog">External blog</a>
<a href="/relative">Relative link</a>
<script>var x = 1;</script>
</body>
</html>
"""


def _fake_response(text="", status_ok=True):
    response = MagicMock()
    response.text = text
    if status_ok:
        response.raise_for_status.return_value = None
    else:
        response.raise_for_status.side_effect = RuntimeError("HTTP error")
    return response


def test_content_collector_happy_path(test_settings):
    collector = ContentCollector(test_settings)

    with patch(
        "provenance.collectors.content.requests.get",
        return_value=_fake_response(_CANNED_HTML),
    ):
        results = collector.collect("https://acme.example.com/")

    by_key = {r.signal_key: r for r in results}
    assert all(r.error is None for r in results)

    assert by_key["heading_count"].signal_value == 2.0
    assert by_key["has_h1"].signal_value == 1.0
    assert by_key["list_count"].signal_value == 2.0
    assert by_key["table_count"].signal_value == 1.0
    assert by_key["external_link_count"].signal_value == 1.0
    assert by_key["has_faq_schema"].signal_value == 1.0
    assert by_key["has_article_schema"].signal_value == 0.0
    assert by_key["has_organization_schema"].signal_value == 0.0
    assert by_key["word_count"].signal_value > 0.0
    assert by_key["statistics_density"].signal_value > 0.0
    assert by_key["title_text"].signal_text == "Acme Graph Database Docs"
    assert by_key["title_text"].signal_value == 0.0


def test_content_collector_degrades_on_request_exception(test_settings):
    collector = ContentCollector(test_settings)

    with patch(
        "provenance.collectors.content.requests.get", side_effect=RuntimeError("network down")
    ):
        results = collector.collect("https://acme.example.com/")

    assert len(results) == 1
    assert results[0].signal_key == "content_error"
    assert results[0].error == "network down"


def test_content_collector_degrades_on_non_200(test_settings):
    collector = ContentCollector(test_settings)

    with patch(
        "provenance.collectors.content.requests.get",
        return_value=_fake_response(status_ok=False),
    ):
        results = collector.collect("https://acme.example.com/")

    assert len(results) == 1
    assert results[0].signal_key == "content_error"
    assert results[0].error == "HTTP error"


def test_content_collector_empty_url_returns_empty_list(test_settings):
    collector = ContentCollector(test_settings)

    with patch("provenance.collectors.content.requests.get") as mock_get:
        results = collector.collect("")

    assert results == []
    mock_get.assert_not_called()


def test_content_collector_missing_title_skips_title_text(test_settings):
    collector = ContentCollector(test_settings)
    html = "<html><body><h1>No title here</h1></body></html>"

    with patch(
        "provenance.collectors.content.requests.get", return_value=_fake_response(html)
    ):
        results = collector.collect("https://acme.example.com/")

    by_key = {r.signal_key: r for r in results}
    assert "title_text" not in by_key


def test_content_collector_existing_signals_unchanged_on_canned_html(test_settings):
    """New signal_keys must not disturb any pre-existing signal on the same
    canned HTML fixture used by the happy-path test."""
    collector = ContentCollector(test_settings)

    with patch(
        "provenance.collectors.content.requests.get",
        return_value=_fake_response(_CANNED_HTML),
    ):
        results = collector.collect("https://acme.example.com/")

    by_key = {r.signal_key: r for r in results}
    assert by_key["heading_count"].signal_value == 2.0
    assert by_key["has_h1"].signal_value == 1.0
    assert by_key["list_count"].signal_value == 2.0
    assert by_key["table_count"].signal_value == 1.0
    assert by_key["external_link_count"].signal_value == 1.0
    assert by_key["statistics_density"].signal_value > 0.0
    assert by_key["title_text"].signal_text == "Acme Graph Database Docs"

    # _CANNED_HTML has no blockquotes and no literal quote characters, so
    # quotation_density is 0; external_citation_density derives from the
    # already-verified external_link_count and word_count.
    assert by_key["quotation_density"].signal_value == 0.0
    word_count = by_key["word_count"].signal_value
    external_links = by_key["external_link_count"].signal_value
    expected_citation_density = round(external_links / word_count * 1000)
    assert by_key["external_citation_density"].signal_value == float(expected_citation_density)


def test_content_collector_quotation_density(test_settings):
    collector = ContentCollector(test_settings)
    html = (
        "<html><body>"
        "<blockquote>Quote one</blockquote>"
        "<blockquote>Quote two</blockquote>"
        '<p>She said "quoted phrase" today.</p>'
        "</body></html>"
    )

    with patch(
        "provenance.collectors.content.requests.get", return_value=_fake_response(html)
    ):
        results = collector.collect("https://acme.example.com/")

    by_key = {r.signal_key: r for r in results}
    # text: "Quote one Quote two She said "quoted phrase" today." -> 9 words.
    # 2 blockquotes + 1 inline quoted pair = 3 quotation occurrences.
    # density = round(3 / 9 * 1000) = 333.
    assert by_key["word_count"].signal_value == 9.0
    assert by_key["quotation_density"].signal_value == 333.0


def test_content_collector_external_citation_density(test_settings):
    collector = ContentCollector(test_settings)
    html = (
        "<html><body>"
        "<p>Hello world this is text.</p>"
        '<a href="https://other.example.com/a">A</a>'
        '<a href="https://other.example.com/b">B</a>'
        '<a href="https://other.example.com/c">C</a>'
        "</body></html>"
    )

    with patch(
        "provenance.collectors.content.requests.get", return_value=_fake_response(html)
    ):
        results = collector.collect("https://acme.example.com/")

    by_key = {r.signal_key: r for r in results}
    # text: "Hello world this is text. A B C" -> 8 words, 3 external links.
    # density = round(3 / 8 * 1000) = 375.
    assert by_key["word_count"].signal_value == 8.0
    assert by_key["external_link_count"].signal_value == 3.0
    assert by_key["external_citation_density"].signal_value == 375.0
