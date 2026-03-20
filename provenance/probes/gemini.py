"""
Gemini probe — stubbed for v1. Drop-in implementation in v2.
"""
from provenance.probes.base import BaseProbe, ProbeContext, ProbeResult, ExtractedEntity
from typing import Optional, List
from datetime import datetime


class GeminiProbe(BaseProbe):
    provider_name = "gemini"

    async def probe(
        self,
        query: str,
        query_variant: str,
        entity_name: str,
        context: ProbeContext,
        competitors: Optional[List[str]] = None,
    ) -> ProbeResult:
        return ProbeResult(
            provider=self.provider_name,
            model=self.settings.gemini_default_model,
            query_text=query,
            query_variant=query_variant,
            raw_response="",
            extracted_entities=[],
            cited_urls=[],
            probed_at=datetime.utcnow(),
            error="Gemini probe is stubbed in v1",
        )

    def _build_prompt(self, query: str, entity_name: str, context: ProbeContext) -> str:
        return query

    def _extract_entities(
        self, raw_response: str, entity_name: str, competitors: List[str]
    ) -> List[ExtractedEntity]:
        return []
