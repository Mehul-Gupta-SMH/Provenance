"""
Social signal collector via the Hacker News Algolia API (keyless, free) —
functional implementation, first collector writing to the DataPoint EAV store
(CLAUDE.md: "DataPoint — the ever-expanding store").

Failure policy (mirrors DemandCollector): any exception (network, timeout, bad
JSON, non-200) is caught and returned as a single-element list with `error`
set — no signal rows are fabricated. Never raises.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import requests

from provenance.collectors.base import BaseCollector
from provenance.config import Settings

_ALGOLIA_SEARCH_URL = "https://hn.algolia.com/api/v1/search"


@dataclass
class SocialSignalResult:
    signal_key: str
    signal_value: float
    signal_text: Optional[str] = None
    error: Optional[str] = None


class SocialCollector(BaseCollector):
    collector_name = "social"

    def __init__(self, settings: Settings):
        super().__init__(settings)

    def collect(self, entity_name: str) -> List[SocialSignalResult]:
        """
        Collect Hacker News story-mention signals for entity_name via the
        Algolia search API.

        Produces: hn_story_count, hn_points_top, hn_points_total,
        hn_comments_total, and (only when there is at least one hit)
        hn_top_story_title as a text-only entry (signal_value=0.0).

        Never raises. Any failure (network, timeout, bad JSON, non-200)
        degrades to a single SocialSignalResult with `error` set.
        """
        try:
            response = requests.get(
                _ALGOLIA_SEARCH_URL,
                params={"query": entity_name, "tags": "story"},
                timeout=self.settings.hn_timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()

            hits = data.get("hits", [])
            points = [int(h.get("points") or 0) for h in hits]
            comments = [int(h.get("num_comments") or 0) for h in hits]

            results = [
                SocialSignalResult(
                    signal_key="hn_story_count", signal_value=float(data.get("nbHits", 0))
                ),
                SocialSignalResult(
                    signal_key="hn_points_top", signal_value=float(max(points) if points else 0)
                ),
                SocialSignalResult(
                    signal_key="hn_points_total", signal_value=float(sum(points))
                ),
                SocialSignalResult(
                    signal_key="hn_comments_total", signal_value=float(sum(comments))
                ),
            ]

            if hits:
                results.append(
                    SocialSignalResult(
                        signal_key="hn_top_story_title",
                        signal_value=0.0,
                        signal_text=hits[0].get("title"),
                    )
                )

            return results

        except Exception as e:
            return [SocialSignalResult(signal_key="hn_error", signal_value=0.0, error=str(e))]
