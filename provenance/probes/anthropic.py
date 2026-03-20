"""
Anthropic/Claude probe — functional implementation (v1).
Full implementation added in Phase 3.
"""
from provenance.probes.base import BaseProbe, ProbeContext, ProbeResult, ExtractedEntity
from typing import Optional, List


class AnthropicProbe(BaseProbe):
    provider_name = "anthropic"

    async def probe(
        self,
        query: str,
        query_variant: str,
        entity_name: str,
        context: ProbeContext,
        competitors: Optional[List[str]] = None,
    ) -> ProbeResult:
        raise NotImplementedError("AnthropicProbe.probe() — implemented in Phase 3")

    def _build_prompt(self, query: str, entity_name: str, context: ProbeContext) -> str:
        raise NotImplementedError

    def _extract_entities(
        self, raw_response: str, entity_name: str, competitors: List[str]
    ) -> List[ExtractedEntity]:
        raise NotImplementedError
