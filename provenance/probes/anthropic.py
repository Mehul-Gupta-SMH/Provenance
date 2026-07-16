"""
Anthropic/Claude probe — functional implementation (v1).

Two-pass design (PLAN.md section 7, "Low-Level Design: Probes"):

  1. Recommendation pass — send a naturalistic query (built by
     ``_build_prompt``, which injects persona / expertise / use-case /
     locale context from ``ProbeContext`` when set, plus
     ``system_prompt_variant``) and record the raw LLM response.
  2. Extraction pass — a second, deterministic LLM call that takes the raw
     response text + entity_name + competitors and returns strict JSON
     describing every entity mentioned. That JSON is parsed into
     ``ExtractedEntity`` objects by ``_extract_entities``.

Soft-failure contract: ``probe()`` never raises. Any exception (auth
failure, exhausted retries, malformed response, ...) is caught and turned
into a ``ProbeResult`` with ``error=str(e)`` and empty extractions.
Rate-limit / timeout / connection / server errors are retried with
exponential backoff up to ``settings.probe_max_retries``; the per-request
timeout is ``settings.probe_timeout_seconds``. Model, API key, and
temperature are always sourced from ``self.settings`` / ``ProbeContext`` —
never hardcoded.
"""
import asyncio
import json
import logging
import re
from datetime import datetime
from typing import Any, List, Optional

import anthropic
from anthropic import AsyncAnthropic

from provenance.probes.base import BaseProbe, ExtractedEntity, ProbeContext, ProbeResult

logger = logging.getLogger(__name__)


# System prompt for the recommendation (naturalistic) pass. Deliberately
# generic — the persona/expertise/use-case/locale steering happens in the
# user-facing query text built by _build_prompt, not here.
_RECOMMENDATION_SYSTEM_PROMPT = (
    "You are a helpful assistant providing honest, candid recommendations. "
    "Answer naturally, as you would to a real user asking this question."
)

# The extraction pass is a deterministic parsing task, not a creative one —
# strict JSON, no prose, no markdown fences.
_EXTRACTION_SYSTEM_PROMPT = """You are a structured data extractor. Given an LLM \
recommendation response and a list of entities, extract exactly what was said \
about each entity. Return JSON only — no prose, no markdown code fences.

Output schema:
{
  "entities": [
    {
      "name": "string",
      "recommendation_rank": null or integer (1 = mentioned first/primary),
      "mention_type": "primary" | "alternative" | "cautionary" | "absent",
      "phrasing_sentiment": "positive" | "neutral" | "qualified" | null,
      "context_of_mention": "string or null",
      "co_mentioned_entities": ["string", ...]
    }
  ]
}
"""

# Errors worth retrying: rate limits and transient connection/server issues.
# Auth/validation errors (AuthenticationError, BadRequestError, ...) are not
# retried — they propagate out of _create_with_retry and are caught by the
# outer soft-failure handler in probe().
_RETRYABLE_EXCEPTIONS = (
    anthropic.RateLimitError,
    anthropic.APITimeoutError,
    anthropic.APIConnectionError,
    anthropic.InternalServerError,
)

_MAX_BACKOFF_SECONDS = 30.0
_FENCE_OPEN_RE = re.compile(r"^```[a-zA-Z]*\n?")
_FENCE_CLOSE_RE = re.compile(r"\n?```$")


class AnthropicProbe(BaseProbe):
    provider_name = "anthropic"

    def __init__(self, settings):
        super().__init__(settings)
        self._client = AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            timeout=settings.probe_timeout_seconds,
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def probe(
        self,
        query: str,
        query_variant: str,
        entity_name: str,
        context: ProbeContext,
        competitors: Optional[List[str]] = None,
    ) -> ProbeResult:
        competitors = competitors or []
        model = self.settings.anthropic_default_model

        try:
            prompt = self._build_prompt(query, entity_name, context)

            response = await self._create_with_retry(
                model=model,
                max_tokens=1500,
                temperature=context.temperature,
                system=_RECOMMENDATION_SYSTEM_PROMPT,
                messages=self._build_messages(prompt, context),
            )
            raw_response = self._response_text(response)

            extracted = await self._run_extraction_pass(raw_response, entity_name, competitors)
            cited_urls = self._extract_urls(raw_response)

            return ProbeResult(
                provider=self.provider_name,
                model=model,
                query_text=query,
                query_variant=query_variant,
                raw_response=raw_response,
                extracted_entities=extracted,
                cited_urls=cited_urls,
                probed_at=datetime.utcnow(),
            )

        except Exception as e:  # soft-failure contract: never raise from probe()
            logger.warning("AnthropicProbe.probe() failed for variant=%s: %s", query_variant, e)
            return ProbeResult(
                provider=self.provider_name,
                model=model,
                query_text=query,
                query_variant=query_variant,
                raw_response="",
                extracted_entities=[],
                cited_urls=[],
                probed_at=datetime.utcnow(),
                error=str(e),
            )

    # ------------------------------------------------------------------
    # Prompt construction
    # ------------------------------------------------------------------

    def _build_prompt(self, query: str, entity_name: str, context: ProbeContext) -> str:
        """
        Build the naturalistic user-facing query sent to the model.

        Layers persona / expertise level / stated use-case / locale context
        from ``ProbeContext`` onto the raw query when those fields are set,
        so the probe reflects the full experimental context even though a
        single user message is sent. ``system_prompt_variant`` is included
        as a lightweight tag so downstream analysis can identify which
        variant produced a given response.
        """
        context_clauses: List[str] = []
        if context.user_persona:
            context_clauses.append(f"I am a {context.user_persona}")
        if context.expertise_level:
            context_clauses.append(f"with {context.expertise_level} expertise in this area")
        if context.stated_use_case:
            context_clauses.append(f"looking to use this for {context.stated_use_case}")
        if context.locale and context.locale != "en-US":
            context_clauses.append(f"based in a {context.locale} locale")

        prefix = ""
        if context_clauses:
            joined = ", ".join(context_clauses)
            prefix = joined[0].upper() + joined[1:] + ".\n\n"

        variant_tag = ""
        if context.system_prompt_variant:
            variant_tag = f"[system_prompt_variant: {context.system_prompt_variant}]\n"

        return f"{variant_tag}{prefix}{query}"

    def _build_messages(self, prompt: str, context: ProbeContext) -> List[dict]:
        """Assemble the messages array, prepending prior_context turns if present."""
        messages: List[dict] = []
        if context.prior_context:
            try:
                prior = json.loads(context.prior_context)
                if isinstance(prior, list):
                    messages.extend(prior)
                else:
                    logger.warning("prior_context JSON was not a list; ignoring")
            except (json.JSONDecodeError, TypeError):
                logger.warning("Ignoring unparseable prior_context JSON")
        messages.append({"role": "user", "content": prompt})
        return messages

    # ------------------------------------------------------------------
    # Extraction pass
    # ------------------------------------------------------------------

    async def _run_extraction_pass(
        self,
        raw_response: str,
        entity_name: str,
        competitors: List[str],
    ) -> List[ExtractedEntity]:
        """
        Issue the extraction-pass LLM call and hand its raw JSON text to
        ``_extract_entities`` for parsing. Extraction failures (API errors,
        exhausted retries) are swallowed here — an extraction problem must
        never take down an otherwise-successful recommendation pass.
        """
        all_entities = [entity_name, *competitors]
        extraction_prompt = (
            "Response to analyze:\n---\n"
            f"{raw_response}\n---\n\n"
            f"Entities to extract: {json.dumps(all_entities)}\n\n"
            "Extract the recommendation signal for each entity. Return JSON only."
        )
        try:
            response = await self._create_with_retry(
                model=self.settings.anthropic_default_model,
                max_tokens=1000,
                temperature=0.0,  # deterministic parsing pass, not creative generation
                system=_EXTRACTION_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": extraction_prompt}],
            )
        except Exception as e:
            logger.warning("Extraction pass API call failed, returning no extractions: %s", e)
            return []

        raw_json_text = self._response_text(response)
        return self._extract_entities(raw_json_text, entity_name, competitors)

    def _extract_entities(
        self,
        raw_response: str,
        entity_name: str,
        competitors: List[str],
    ) -> List[ExtractedEntity]:
        """
        Parse the extraction pass's JSON output into ``ExtractedEntity``
        objects. Defensive: strips markdown fences, tolerates missing keys,
        and returns ``[]`` (never raises) on unparseable JSON.
        """
        data = self._parse_json_object(raw_response)
        if data is None:
            return []

        entities = data.get("entities")
        if not isinstance(entities, list):
            return []

        results: List[ExtractedEntity] = []
        for item in entities:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not name:
                continue

            co_mentioned = item.get("co_mentioned_entities", [])
            if not isinstance(co_mentioned, list):
                co_mentioned = []

            mention_type = item.get("mention_type") or "absent"
            rank = item.get("recommendation_rank")
            if not isinstance(rank, int):
                rank = None

            results.append(
                ExtractedEntity(
                    name=str(name),
                    recommendation_rank=rank,
                    mention_type=str(mention_type),
                    phrasing_sentiment=item.get("phrasing_sentiment"),
                    context_of_mention=item.get("context_of_mention"),
                    co_mentioned_entities=[str(x) for x in co_mentioned],
                )
            )
        return results

    @staticmethod
    def _parse_json_object(text: str) -> Optional[dict]:
        """Strip markdown fences and parse JSON; return None (never raise) on failure."""
        if not text:
            return None

        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = _FENCE_OPEN_RE.sub("", stripped)
            stripped = _FENCE_CLOSE_RE.sub("", stripped)
            stripped = stripped.strip()

        try:
            parsed = json.loads(stripped)
        except (json.JSONDecodeError, TypeError, ValueError):
            return None

        if not isinstance(parsed, dict):
            return None
        return parsed

    # ------------------------------------------------------------------
    # API call helper with retry / backoff
    # ------------------------------------------------------------------

    async def _create_with_retry(self, **kwargs: Any):
        """
        Call ``messages.create`` with exponential backoff on retryable
        (rate-limit / timeout / connection / server) errors, up to
        ``settings.probe_max_retries`` additional attempts. Non-retryable
        errors (auth, bad request, ...) propagate immediately.
        """
        max_retries = max(self.settings.probe_max_retries, 0)
        last_exc: Optional[Exception] = None

        for attempt in range(max_retries + 1):
            try:
                return await self._client.messages.create(**kwargs)
            except _RETRYABLE_EXCEPTIONS as exc:
                last_exc = exc
                if attempt >= max_retries:
                    break
                delay = min(2.0**attempt, _MAX_BACKOFF_SECONDS)
                logger.warning(
                    "Anthropic API call failed (attempt %d/%d): %s — retrying in %.1fs",
                    attempt + 1,
                    max_retries + 1,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)

        assert last_exc is not None  # loop always sets it before breaking/exhausting
        raise last_exc

    @staticmethod
    def _response_text(response: Any) -> str:
        """Extract text from the first text content block; defensive against empty content."""
        for block in getattr(response, "content", None) or []:
            if getattr(block, "type", None) == "text":
                return block.text
        return ""
