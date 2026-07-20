"""
Discoverability collector — audits an entity's site for AI-discoverability
(robots.txt AI-bot access, llms.txt, JSON-LD schema, .well-known AI endpoints)
and writes to the DataPoint EAV store (CLAUDE.md: "DataPoint — the
ever-expanding store"). Ports the embedded rubric in docs/roadmap.md
("Discoverability score — 8 weighted categories", geo-optimizer-skill).

Failure policy (mirrors ContentCollector/SocialCollector): the whole collect()
call is wrapped in one try/except, exactly like ContentCollector. A real
exception (network down, timeout, unparseable url) is caught and returned as a
single-element list with `error` set — no signal rows are fabricated. Never
raises. A falsy entity_url means there is nothing to fetch, so collect()
returns [] without a network call. A non-200 response for any one endpoint
(robots.txt/llms.txt/homepage/.well-known) is NOT an exception — it degrades
only that endpoint's signal(s) to an "absent" default while the other
endpoints are still fetched normally.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

from provenance.collectors.base import BaseCollector
from provenance.collectors.content import ContentCollector
from provenance.config import Settings

# The four "citation bots" (docs/roadmap.md: "robots.txt weighting hinges on the
# four citation bots specifically ... being allowed, not just any AI bot").
CITATION_BOTS = {"OAI-SearchBot", "ClaudeBot", "Claude-SearchBot", "PerplexityBot"}

# A reasonable subset of well-known AI training/crawling bots (not exhaustive).
TRAINING_BOTS = {
    "GPTBot",
    "anthropic-ai",
    "Google-Extended",
    "CCBot",
    "Bytespider",
    "PerplexityBot",
    "ClaudeBot",
    "Applebot-Extended",
    "meta-externalagent",
    "cohere-ai",
}

# schema.org types that count toward schema_richness_score (0..4).
_RICHNESS_TYPES = {"WebSite", "Organization", "FAQPage", "Article"}

_LLMS_TXT_DEPTH_CAP = 10

_WELL_KNOWN_PATHS = ("/.well-known/ai.txt", "/ai/summary.json")

_JSONLD_SCRIPT_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)
_HEADING_RE = re.compile(r"^#{1,6}\s", re.MULTILINE)
_TITLE_RE = re.compile(r"<title[^>]*>.*?</title>", re.IGNORECASE | re.DOTALL)
_META_DESC_RE = re.compile(r'<meta[^>]+name=["\']description["\']', re.IGNORECASE)
_CANONICAL_RE = re.compile(r'<link[^>]+rel=["\']canonical["\']', re.IGNORECASE)
_OG_TITLE_RE = re.compile(r'<meta[^>]+property=["\']og:title["\']', re.IGNORECASE)


@dataclass
class DiscoverabilitySignalResult:
    signal_key: str
    signal_value: float
    signal_text: Optional[str] = None
    error: Optional[str] = None


class DiscoverabilityCollector(BaseCollector):
    collector_name = "discoverability"

    def __init__(self, settings: Settings):
        super().__init__(settings)

    def collect(self, entity_url: str) -> List[DiscoverabilitySignalResult]:
        """
        Audit the entity's origin (derived from entity_url) for AI-discoverability.

        Produces: robots_txt_present, robots_citation_bots_allowed,
        robots_training_bots_allowed, llms_txt_present, llms_txt_depth_score,
        llms_full_txt_present, schema_types_present (text-only), schema_richness_score,
        meta_score, ai_discovery_score.

        Never raises. A falsy entity_url returns [] — nothing to fetch. Any
        exception (network, timeout, unparseable url) degrades to a single
        DiscoverabilitySignalResult with `error` set. A non-200 response for one
        endpoint only degrades that endpoint's own signal(s) to "absent".
        """
        if not entity_url:
            return []

        try:
            parsed = urlparse(entity_url)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError(f"Cannot derive origin from url: {entity_url}")
            origin = f"{parsed.scheme}://{parsed.netloc}"

            results: List[DiscoverabilitySignalResult] = []
            results.extend(self._collect_robots(origin))
            results.extend(self._collect_llms_txt(origin))
            results.extend(self._collect_schema_and_meta(origin))
            results.extend(self._collect_well_known(origin))
            return results

        except Exception as e:
            return [
                DiscoverabilitySignalResult(
                    signal_key="discoverability_error", signal_value=0.0, error=str(e)
                )
            ]

    # ------------------------------------------------------------------
    # robots.txt — citation-bot / training-bot access tiers
    # ------------------------------------------------------------------

    def _collect_robots(self, origin: str) -> List[DiscoverabilitySignalResult]:
        response = requests.get(
            f"{origin}/robots.txt", timeout=self.settings.discoverability_timeout_seconds
        )
        if response.status_code != 200:
            # No robots.txt means nothing disallows any bot.
            return [
                DiscoverabilitySignalResult(signal_key="robots_txt_present", signal_value=0.0),
                DiscoverabilitySignalResult(
                    signal_key="robots_citation_bots_allowed", signal_value=1.0
                ),
                DiscoverabilitySignalResult(
                    signal_key="robots_training_bots_allowed", signal_value=1.0
                ),
            ]

        rp = RobotFileParser()
        rp.parse(response.text.splitlines())
        citation_allowed = sum(1 for bot in CITATION_BOTS if rp.can_fetch(bot, "/")) / len(
            CITATION_BOTS
        )
        training_allowed = sum(1 for bot in TRAINING_BOTS if rp.can_fetch(bot, "/")) / len(
            TRAINING_BOTS
        )
        return [
            DiscoverabilitySignalResult(signal_key="robots_txt_present", signal_value=1.0),
            DiscoverabilitySignalResult(
                signal_key="robots_citation_bots_allowed", signal_value=citation_allowed
            ),
            DiscoverabilitySignalResult(
                signal_key="robots_training_bots_allowed", signal_value=training_allowed
            ),
        ]

    # ------------------------------------------------------------------
    # llms.txt / llms-full.txt
    # ------------------------------------------------------------------

    def _collect_llms_txt(self, origin: str) -> List[DiscoverabilitySignalResult]:
        response = requests.get(
            f"{origin}/llms.txt", timeout=self.settings.discoverability_timeout_seconds
        )
        if response.status_code == 200:
            heading_count = len(_HEADING_RE.findall(response.text))
            present, depth_score = 1.0, float(min(heading_count, _LLMS_TXT_DEPTH_CAP))
        else:
            present, depth_score = 0.0, 0.0

        full_response = requests.get(
            f"{origin}/llms-full.txt", timeout=self.settings.discoverability_timeout_seconds
        )
        full_present = 1.0 if full_response.status_code == 200 else 0.0

        return [
            DiscoverabilitySignalResult(signal_key="llms_txt_present", signal_value=present),
            DiscoverabilitySignalResult(
                signal_key="llms_txt_depth_score", signal_value=depth_score
            ),
            DiscoverabilitySignalResult(
                signal_key="llms_full_txt_present", signal_value=full_present
            ),
        ]

    # ------------------------------------------------------------------
    # Homepage HTML — JSON-LD schema + meta tags
    # ------------------------------------------------------------------

    def _collect_schema_and_meta(self, origin: str) -> List[DiscoverabilitySignalResult]:
        response = requests.get(
            f"{origin}/", timeout=self.settings.discoverability_timeout_seconds
        )
        if response.status_code != 200:
            return [
                DiscoverabilitySignalResult(
                    signal_key="schema_types_present", signal_value=0.0, signal_text=""
                ),
                DiscoverabilitySignalResult(signal_key="schema_richness_score", signal_value=0.0),
                DiscoverabilitySignalResult(signal_key="meta_score", signal_value=0.0),
            ]

        html_text = response.text
        jsonld_blocks = _JSONLD_SCRIPT_RE.findall(html_text)
        schema_types = ContentCollector._extract_jsonld_types(jsonld_blocks)
        richness = float(sum(1 for t in _RICHNESS_TYPES if t in schema_types))

        meta_present = sum(
            1
            for pattern in (_TITLE_RE, _META_DESC_RE, _CANONICAL_RE, _OG_TITLE_RE)
            if pattern.search(html_text)
        )
        meta_score = meta_present / 4

        return [
            DiscoverabilitySignalResult(
                signal_key="schema_types_present",
                signal_value=0.0,
                signal_text=",".join(sorted(schema_types)),
            ),
            DiscoverabilitySignalResult(signal_key="schema_richness_score", signal_value=richness),
            DiscoverabilitySignalResult(signal_key="meta_score", signal_value=meta_score),
        ]

    # ------------------------------------------------------------------
    # .well-known AI discovery endpoints
    # ------------------------------------------------------------------

    def _collect_well_known(self, origin: str) -> List[DiscoverabilitySignalResult]:
        present_count = 0
        for path in _WELL_KNOWN_PATHS:
            response = requests.get(
                f"{origin}{path}", timeout=self.settings.discoverability_timeout_seconds
            )
            if response.status_code == 200:
                present_count += 1
        return [
            DiscoverabilitySignalResult(
                signal_key="ai_discovery_score",
                signal_value=present_count / len(_WELL_KNOWN_PATHS),
            )
        ]
