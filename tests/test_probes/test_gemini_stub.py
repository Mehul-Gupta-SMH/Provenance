"""Tests for provenance/probes/gemini.py (PLAN.md section 14, Probes 4 analogue)."""
from __future__ import annotations

import pytest

from provenance.probes.base import ProbeContext
from provenance.probes.gemini import GeminiProbe


@pytest.mark.asyncio
async def test_gemini_probe_returns_stub_error(test_settings):
    probe = GeminiProbe(test_settings)

    result = await probe.probe(
        query="What is the best graph database?",
        query_variant="direct",
        entity_name="Acme",
        context=ProbeContext(),
    )

    assert result.provider == "gemini"
    assert result.model == test_settings.gemini_default_model
    assert result.error == "Gemini probe is stubbed in v1"
    assert result.extracted_entities == []
    assert result.cited_urls == []
    assert result.raw_response == ""
