"""
Anthropic/Claude probe — functional implementation (v1).

Extraction strategy: system prompt asks Claude to answer naturally, then append
a fenced ```json block with structured entity assessments. One API call per probe.
"""
import json
import logging
import re
from datetime import datetime
from typing import List, Optional

import anthropic as anthropic_sdk

from provenance.probes.base import BaseProbe, ExtractedEntity, ProbeContext, ProbeResult

logger = logging.getLogger(__name__)

# Embedded in every system prompt. Instructs Claude to answer naturally and then
# append a structured JSON block that we parse for signal extraction.
_EXTRACTION_INSTRUCTION = """
After your answer, append a fenced JSON block (```json ... ```) with this exact structure:
{
  "entities_mentioned": [
    {
      "name": "exact entity name as you wrote it",
      "rank": 1,
      "mention_type": "primary",
      "sentiment": "positive",
      "context": "one sentence describing how it was mentioned"
    }
  ],
  "cited_urls": []
}

Field rules:
- mention_type: "primary" (top recommendation), "alternative" (secondary option), "cautionary" (warned against). Omit entities not mentioned.
- sentiment: "positive", "neutral", or "qualified" (mixed/conditional praise).
- rank: 1-based integer for explicit recommendations; null if no explicit ranking.
- cited_urls: any URLs you reference in your answer.
"""

_BASE_SYSTEM_PROMPT = (
    "You are a knowledgeable, unbiased advisor helping evaluate technologies, tools, "
    "and services. Answer the user's question naturally and helpfully."
    + _EXTRACTION_INSTRUCTION
)


class AnthropicProbe(BaseProbe):
    provider_name = "anthropic"

    def __init__(self, settings):
        super().__init__(settings)
        self._client = anthropic_sdk.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def probe(
        self,
        query: str,
        query_variant: str,
        entity_name: str,
        context: ProbeContext,
        competitors: Optional[List[str]] = None,
    ) -> ProbeResult:
        competitors = competitors or []
        try:
            system = self._build_prompt(query, entity_name, context)
            response = await self._client.messages.create(
                model=self.settings.anthropic_default_model,
                max_tokens=1024,
                temperature=context.temperature,
                system=system,
                messages=[{"role": "user", "content": query}],
            )
            raw = response.content[0].text
            return ProbeResult(
                provider=self.provider_name,
                model=self.settings.anthropic_default_model,
                query_text=query,
                query_variant=query_variant,
                raw_response=raw,
                extracted_entities=self._extract_entities(raw, entity_name, competitors),
                cited_urls=self._extract_urls(raw),
                probed_at=datetime.utcnow(),
            )
        except Exception as exc:
            logger.warning("AnthropicProbe error (variant=%s): %s", query_variant, exc)
            return ProbeResult(
                provider=self.provider_name,
                model=self.settings.anthropic_default_model,
                query_text=query,
                query_variant=query_variant,
                raw_response="",
                extracted_entities=[],
                cited_urls=[],
                probed_at=datetime.utcnow(),
                error=str(exc),
            )

    def _build_prompt(self, query: str, entity_name: str, context: ProbeContext) -> str:
        parts = [_BASE_SYSTEM_PROMPT]
        if context.user_persona:
            parts.append(f"The user identifies as: {context.user_persona}.")
        if context.expertise_level:
            parts.append(f"User expertise level: {context.expertise_level}.")
        if context.stated_use_case:
            parts.append(f"Use case context: {context.stated_use_case}.")
        return "\n".join(parts)

    def _extract_entities(
        self,
        raw_response: str,
        entity_name: str,
        competitors: List[str],
    ) -> List[ExtractedEntity]:
        block = self._parse_json_block(raw_response)
        if block is None:
            return []
        results = []
        all_names = {entity_name, *competitors}
        for item in block.get("entities_mentioned", []):
            name = item.get("name", "")
            co_mentioned = [n for n in all_names if n != name]
            results.append(
                ExtractedEntity(
                    name=name,
                    recommendation_rank=item.get("rank"),
                    mention_type=item.get("mention_type", "absent"),
                    phrasing_sentiment=item.get("sentiment"),
                    context_of_mention=item.get("context"),
                    co_mentioned_entities=co_mentioned,
                )
            )
        return results

    def _extract_urls(self, raw_response: str) -> List[str]:
        block = self._parse_json_block(raw_response)
        if block:
            urls = block.get("cited_urls", [])
            if urls:
                return urls
        return super()._extract_urls(raw_response)

    @staticmethod
    def _parse_json_block(text: str) -> Optional[dict]:
        match = re.search(r"```json\s*([\s\S]*?)```", text)
        if not match:
            return None
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
