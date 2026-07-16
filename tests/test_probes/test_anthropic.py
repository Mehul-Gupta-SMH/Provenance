"""Tests for provenance/probes/anthropic.py (PLAN.md section 14, Probes 1-3)."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import anthropic
import httpx
import pytest

from provenance.probes.anthropic import AnthropicProbe
from provenance.probes.base import ProbeContext


def _text_response(text: str) -> SimpleNamespace:
    """Build a fake anthropic Message response with a single text content block."""
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


@pytest.mark.asyncio
async def test_probe_happy_path(test_settings):
    """probe() populates ProbeResult from the recommendation + extraction passes."""
    probe = AnthropicProbe(test_settings)

    extraction_json = json.dumps(
        {
            "entities": [
                {
                    "name": "Acme",
                    "recommendation_rank": 1,
                    "mention_type": "primary",
                    "phrasing_sentiment": "positive",
                    "context_of_mention": "top pick",
                    "co_mentioned_entities": ["Rival"],
                }
            ]
        }
    )
    probe._client.messages.create = AsyncMock(
        side_effect=[
            _text_response("Acme is the best choice. See https://acme.example.com/docs."),
            _text_response(extraction_json),
        ]
    )

    result = await probe.probe(
        query="What is the best graph database?",
        query_variant="direct",
        entity_name="Acme",
        context=ProbeContext(),
        competitors=["Rival"],
    )

    assert result.error is None
    assert result.provider == "anthropic"
    assert result.model == test_settings.anthropic_default_model
    assert "Acme is the best choice" in result.raw_response
    assert result.cited_urls == ["https://acme.example.com/docs."]
    assert len(result.extracted_entities) == 1
    entity = result.extracted_entities[0]
    assert entity.name == "Acme"
    assert entity.recommendation_rank == 1
    assert entity.mention_type == "primary"
    assert entity.co_mentioned_entities == ["Rival"]
    assert probe._client.messages.create.call_count == 2


def test_extract_entities_parses_canned_json(test_settings):
    """_extract_entities() parses a canned extraction response into ExtractedEntity objects."""
    probe = AnthropicProbe(test_settings)
    raw = json.dumps(
        {
            "entities": [
                {
                    "name": "Acme",
                    "recommendation_rank": 2,
                    "mention_type": "alternative",
                    "phrasing_sentiment": "neutral",
                    "context_of_mention": "mentioned as an option",
                    "co_mentioned_entities": ["Rival", "Other"],
                }
            ]
        }
    )

    entities = probe._extract_entities(raw, "Acme", ["Rival", "Other"])

    assert len(entities) == 1
    assert entities[0].name == "Acme"
    assert entities[0].recommendation_rank == 2
    assert entities[0].mention_type == "alternative"
    assert entities[0].co_mentioned_entities == ["Rival", "Other"]


def test_extract_entities_malformed_json_returns_empty_list(test_settings):
    """Malformed/non-JSON extraction output never raises — it degrades to []."""
    probe = AnthropicProbe(test_settings)

    assert probe._extract_entities("not json at all {{{", "Acme", []) == []
    assert probe._extract_entities("", "Acme", []) == []
    assert probe._extract_entities(json.dumps({"entities": "not-a-list"}), "Acme", []) == []


@pytest.mark.asyncio
async def test_probe_soft_fails_on_api_error(test_settings):
    """A raised API error is caught — probe() returns a ProbeResult with error set."""
    probe = AnthropicProbe(test_settings)
    probe._client.messages.create = AsyncMock(side_effect=RuntimeError("auth failed"))

    result = await probe.probe(
        query="What is the best graph database?",
        query_variant="direct",
        entity_name="Acme",
        context=ProbeContext(),
    )

    assert result.error == "auth failed"
    assert result.raw_response == ""
    assert result.extracted_entities == []
    assert result.cited_urls == []


@pytest.mark.asyncio
async def test_probe_retries_exhausted_soft_fails(test_settings, monkeypatch):
    """Retryable errors are retried up to probe_max_retries, then soft-fail (no raise)."""
    monkeypatch.setattr(
        "provenance.probes.anthropic.asyncio.sleep", AsyncMock(return_value=None)
    )
    probe = AnthropicProbe(test_settings)
    timeout_request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    probe._client.messages.create = AsyncMock(
        side_effect=anthropic.APITimeoutError(request=timeout_request)
    )

    result = await probe.probe(
        query="What is the best graph database?",
        query_variant="direct",
        entity_name="Acme",
        context=ProbeContext(),
    )

    assert result.error is not None
    # probe_max_retries=1 in test_settings -> 2 total attempts (initial + 1 retry)
    assert probe._client.messages.create.call_count == test_settings.probe_max_retries + 1
