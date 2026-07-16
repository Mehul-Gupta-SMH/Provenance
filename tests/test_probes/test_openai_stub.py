"""Tests for provenance/probes/openai.py (PLAN.md section 14, Probes 4)."""
from __future__ import annotations

import pytest

from provenance.probes.base import ProbeContext
from provenance.probes.openai import OpenAIProbe


@pytest.mark.asyncio
async def test_openai_probe_returns_stub_error(test_settings):
    probe = OpenAIProbe(test_settings)

    result = await probe.probe(
        query="What is the best graph database?",
        query_variant="direct",
        entity_name="Acme",
        context=ProbeContext(),
    )

    assert result.provider == "openai"
    assert result.model == test_settings.openai_default_model
    assert result.error == "OpenAI probe is stubbed in v1"
    assert result.extracted_entities == []
    assert result.cited_urls == []
    assert result.raw_response == ""
