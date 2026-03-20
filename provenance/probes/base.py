from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime


@dataclass
class ProbeContext:
    """All context parameters for a single LLM probe call."""
    country: str = "US"
    region: Optional[str] = None
    language: str = "en"
    locale: str = "en-US"
    user_persona: Optional[str] = None
    expertise_level: Optional[str] = None
    stated_use_case: Optional[str] = None
    temperature: float = 0.2
    system_prompt_variant: Optional[str] = None
    prior_context: Optional[str] = None  # JSON string of conversation history


@dataclass
class ExtractedEntity:
    """Single entity extraction result from a probe response."""
    name: str
    recommendation_rank: Optional[int]
    mention_type: str  # "primary" | "alternative" | "cautionary" | "absent"
    phrasing_sentiment: Optional[str]
    context_of_mention: Optional[str]
    co_mentioned_entities: List[str] = field(default_factory=list)


@dataclass
class ProbeResult:
    """Normalized output of a single LLM probe call."""
    provider: str
    model: str
    query_text: str
    query_variant: str
    raw_response: str
    extracted_entities: List[ExtractedEntity]
    cited_urls: List[str]
    probed_at: datetime = field(default_factory=datetime.utcnow)
    error: Optional[str] = None


class BaseProbe(ABC):
    """Abstract base for all LLM probe implementations."""

    provider_name: str  # class-level constant, e.g. "anthropic"

    def __init__(self, settings):
        self.settings = settings

    @abstractmethod
    async def probe(
        self,
        query: str,
        query_variant: str,
        entity_name: str,
        context: ProbeContext,
        competitors: Optional[List[str]] = None,
    ) -> ProbeResult:
        """
        Execute a single LLM probe.
        Must return a ProbeResult even on soft failures (set error field).
        Raise only on unrecoverable errors.
        """
        ...

    @abstractmethod
    def _build_prompt(self, query: str, entity_name: str, context: ProbeContext) -> str:
        """Build the full prompt string for this probe."""
        ...

    @abstractmethod
    def _extract_entities(
        self,
        raw_response: str,
        entity_name: str,
        competitors: List[str],
    ) -> List[ExtractedEntity]:
        """Parse the raw LLM response into structured ExtractedEntity objects."""
        ...

    def _extract_urls(self, raw_response: str) -> List[str]:
        """Default URL extraction via regex. Probes may override for structured citations."""
        import re
        url_pattern = r'https?://[^\s\)\]\>"\'<]+'
        return list(set(re.findall(url_pattern, raw_response)))
