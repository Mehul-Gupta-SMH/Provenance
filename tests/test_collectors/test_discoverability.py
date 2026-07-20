"""Tests for provenance/collectors/discoverability.py (discoverability collector)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from provenance.collectors.discoverability import DiscoverabilityCollector

_ROBOTS_TXT = """
User-agent: OAI-SearchBot
Allow: /

User-agent: ClaudeBot
Disallow: /

User-agent: *
Allow: /
"""

_LLMS_TXT = """# LLMs.txt
## Section A
## Section B
### Sub-section
"""

_HOMEPAGE_HTML = """
<html>
<head>
<title>Acme</title>
<meta name="description" content="Acme docs">
<link rel="canonical" href="https://acme.example.com/">
<meta property="og:title" content="Acme">
<script type="application/ld+json">
{"@context": "https://schema.org", "@type": "Organization", "name": "Acme"}
</script>
<script type="application/ld+json">
{"@context": "https://schema.org", "@type": "FAQPage", "name": "FAQ"}
</script>
</head>
<body></body>
</html>
"""


def _response(status_code=200, text=""):
    response = MagicMock()
    response.status_code = status_code
    response.text = text
    return response


def _fake_get_factory(overrides=None):
    """Returns a requests.get side_effect that serves canned responses keyed by
    URL suffix, with everything present-and-happy by default. `overrides` maps
    a URL suffix to a status_code to force absent for that one endpoint."""
    overrides = overrides or {}

    def fake_get(url, timeout=None):
        if url.endswith("/robots.txt"):
            return _response(overrides.get("/robots.txt", 200), _ROBOTS_TXT)
        if url.endswith("/llms-full.txt"):
            return _response(overrides.get("/llms-full.txt", 404), "")
        if url.endswith("/llms.txt"):
            return _response(overrides.get("/llms.txt", 200), _LLMS_TXT)
        if url.endswith("/.well-known/ai.txt"):
            return _response(overrides.get("/.well-known/ai.txt", 200), "ai discovery")
        if url.endswith("/ai/summary.json"):
            return _response(overrides.get("/ai/summary.json", 404), "")
        if url.endswith("/"):
            return _response(overrides.get("/", 200), _HOMEPAGE_HTML)
        raise AssertionError(f"unexpected URL: {url}")

    return fake_get


def test_discoverability_collector_happy_path(test_settings):
    collector = DiscoverabilityCollector(test_settings)

    with patch(
        "provenance.collectors.discoverability.requests.get",
        side_effect=_fake_get_factory(),
    ):
        results = collector.collect("https://acme.example.com/")

    by_key = {r.signal_key: r for r in results}
    assert all(r.error is None for r in results)

    # robots.txt: OAI-SearchBot + Claude-SearchBot (wildcard) + PerplexityBot
    # (wildcard) allowed, ClaudeBot explicitly disallowed -> 3/4.
    assert by_key["robots_txt_present"].signal_value == 1.0
    assert by_key["robots_citation_bots_allowed"].signal_value == 0.75

    assert by_key["llms_txt_present"].signal_value == 1.0
    assert by_key["llms_txt_depth_score"].signal_value == 4.0
    assert by_key["llms_full_txt_present"].signal_value == 0.0

    assert by_key["schema_types_present"].signal_text == "FAQPage,Organization"
    assert by_key["schema_richness_score"].signal_value == 2.0
    assert by_key["meta_score"].signal_value == 1.0

    # ai.txt present, summary.json absent -> 1/2.
    assert by_key["ai_discovery_score"].signal_value == 0.5


def test_discoverability_collector_degrades_on_unreachable_origin(test_settings):
    collector = DiscoverabilityCollector(test_settings)

    with patch(
        "provenance.collectors.discoverability.requests.get",
        side_effect=RuntimeError("origin unreachable"),
    ):
        results = collector.collect("https://acme.example.com/")

    assert len(results) == 1
    assert results[0].signal_key == "discoverability_error"
    assert results[0].error == "origin unreachable"


def test_discoverability_collector_empty_url_returns_empty_list(test_settings):
    collector = DiscoverabilityCollector(test_settings)

    with patch("provenance.collectors.discoverability.requests.get") as mock_get:
        results = collector.collect("")

    assert results == []
    mock_get.assert_not_called()


def test_discoverability_collector_missing_robots_txt_defaults_bots_allowed(test_settings):
    collector = DiscoverabilityCollector(test_settings)

    with patch(
        "provenance.collectors.discoverability.requests.get",
        side_effect=_fake_get_factory(overrides={"/robots.txt": 404}),
    ):
        results = collector.collect("https://acme.example.com/")

    by_key = {r.signal_key: r for r in results}
    assert by_key["robots_txt_present"].signal_value == 0.0
    assert by_key["robots_citation_bots_allowed"].signal_value == 1.0
    assert by_key["robots_training_bots_allowed"].signal_value == 1.0
