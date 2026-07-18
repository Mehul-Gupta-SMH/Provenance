"""Tests for provenance/collectors/social.py (Hacker News Algolia collector)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from provenance.collectors.social import SocialCollector


def _fake_response(json_data=None, status_ok=True):
    response = MagicMock()
    response.json.return_value = json_data or {}
    if status_ok:
        response.raise_for_status.return_value = None
    else:
        response.raise_for_status.side_effect = RuntimeError("HTTP error")
    return response


def test_social_collector_happy_path(test_settings):
    collector = SocialCollector(test_settings)
    payload = {
        "nbHits": 3,
        "hits": [
            {"points": 100, "num_comments": 20, "title": "Acme launches new thing"},
            {"points": 50, "num_comments": 5, "title": "Acme is great"},
            {"points": 10, "num_comments": 1, "title": "Acme vs Rival"},
        ],
    }

    with patch("provenance.collectors.social.requests.get", return_value=_fake_response(payload)):
        results = collector.collect("Acme")

    by_key = {r.signal_key: r for r in results}
    assert by_key["hn_story_count"].signal_value == 3.0
    assert by_key["hn_points_top"].signal_value == 100.0
    assert by_key["hn_points_total"].signal_value == 160.0
    assert by_key["hn_comments_total"].signal_value == 26.0
    assert by_key["hn_top_story_title"].signal_text == "Acme launches new thing"
    assert by_key["hn_top_story_title"].signal_value == 0.0
    assert all(r.error is None for r in results)


def test_social_collector_no_hits_skips_top_story_title(test_settings):
    collector = SocialCollector(test_settings)
    payload = {"nbHits": 0, "hits": []}

    with patch("provenance.collectors.social.requests.get", return_value=_fake_response(payload)):
        results = collector.collect("Acme")

    by_key = {r.signal_key: r for r in results}
    assert "hn_top_story_title" not in by_key
    assert by_key["hn_story_count"].signal_value == 0.0
    assert by_key["hn_points_top"].signal_value == 0.0
    assert by_key["hn_points_total"].signal_value == 0.0
    assert by_key["hn_comments_total"].signal_value == 0.0


def test_social_collector_degrades_on_request_exception(test_settings):
    collector = SocialCollector(test_settings)

    with patch(
        "provenance.collectors.social.requests.get", side_effect=RuntimeError("network down")
    ):
        results = collector.collect("Acme")

    assert len(results) == 1
    assert results[0].error == "network down"


def test_social_collector_degrades_on_non_200(test_settings):
    collector = SocialCollector(test_settings)

    with patch(
        "provenance.collectors.social.requests.get",
        return_value=_fake_response(status_ok=False),
    ):
        results = collector.collect("Acme")

    assert len(results) == 1
    assert results[0].error == "HTTP error"
