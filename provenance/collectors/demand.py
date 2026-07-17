"""
Demand signal collector via pytrends (Google Trends) — functional implementation (v1).

Failure policy (PLAN.md v1.1, Risk 1): pytrends hits an unofficial, unstable Google API
with no SLA and aggressive rate limiting. This collector must never raise — every pytrends
call happens inside a single guarded region, and any failure (429 rate limit, network
error, timeout, empty/malformed data) degrades to a DemandResult with `error` set and all
signal fields left at their None/empty defaults. A run with missing demand data is still
valid; downstream divergence computation tolerates partial data.
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional

from pytrends.request import TrendReq

from provenance.collectors.base import BaseCollector, DemandResult
from provenance.config import Settings

# Timeframe wide enough to compute a 30-day-vs-prior-30-day trend_velocity from a single
# interest_over_time() frame. Google Trends returns daily-resolution data for windows up to
# ~269 days, so "today 3-m" (~90 days) comfortably covers two 30-day windows.
_TIMEFRAME = "today 3-m"
_MIN_POINTS_FOR_VELOCITY = 60
_TOP_N_RELATED = 5
_TOP_N_REGIONS = 5


class DemandCollector(BaseCollector):
    collector_name = "demand"

    def __init__(self, settings: Settings):
        super().__init__(settings)
        # Lazily constructed. TrendReq.__init__ performs a network call (GetGoogleCookie),
        # so building it eagerly in __init__ would let a network failure raise out of
        # DemandCollector(settings) itself, before collect()'s try/except is entered —
        # violating the "never raise" failure policy. Deferring construction into collect()
        # keeps every pytrends call (including client construction) inside the guarded region.
        self._pytrends: Optional[TrendReq] = None

    def _client(self) -> TrendReq:
        if self._pytrends is None:
            self._pytrends = TrendReq(
                hl="en-US",
                tz=360,
                timeout=(self.settings.pytrends_timeout, self.settings.pytrends_timeout),
            )
        return self._pytrends

    def collect(self, entity_name: str, category: str) -> DemandResult:
        """
        Collect demand signals for entity_name via pytrends.

        - search_volume: mean of the interest_over_time series for the queried period,
          0-100 relative interest.
        - trend_velocity: signed delta of mean(last 30 days) - mean(prior 30 days),
          computed from that same interest_over_time frame.
        - related_queries: top 5 rising related queries.
        - geographic_distribution: top 5 regions by relative interest.

        `category` is accepted for interface/future use — pytrends `cat` is an integer
        category id, not free text, so it is not passed through as a keyword filter in v1.

        Never raises. Any pytrends failure (rate limit, network, timeout, empty/malformed
        data) is caught and returned as DemandResult(error=...) with signal fields left at
        their None/empty defaults.
        """
        delay = self.settings.pytrends_request_delay_seconds
        try:
            pytrends = self._client()

            pytrends.build_payload(
                kw_list=[entity_name],
                cat=0,
                timeframe=_TIMEFRAME,
                geo="",
            )
            time.sleep(delay)

            iot_df = pytrends.interest_over_time()
            if iot_df is None or iot_df.empty or entity_name not in iot_df.columns:
                return DemandResult(
                    entity_name=entity_name,
                    search_volume=None,
                    trend_velocity=None,
                    error="pytrends returned no interest_over_time data",
                )

            values = [float(v) for v in iot_df[entity_name].tolist()]
            search_volume = round(sum(values) / len(values), 2) if values else None

            trend_velocity: Optional[float] = None
            if len(values) >= _MIN_POINTS_FOR_VELOCITY:
                recent_30 = values[-30:]
                prior_30 = values[-60:-30]
                trend_velocity = round(
                    (sum(recent_30) / len(recent_30)) - (sum(prior_30) / len(prior_30)), 2
                )

            time.sleep(delay)
            related = pytrends.related_queries() or {}
            related_queries: List[str] = []
            rising = (related.get(entity_name) or {}).get("rising")
            if rising is not None and not rising.empty:
                related_queries = rising["query"].head(_TOP_N_RELATED).tolist()

            time.sleep(delay)
            regional = pytrends.interest_by_region(resolution="COUNTRY", inc_low_vol=False)
            geographic_distribution: Dict[str, float] = {}
            if (
                regional is not None
                and not regional.empty
                and entity_name in regional.columns
            ):
                top_regions = (
                    regional[entity_name].sort_values(ascending=False).head(_TOP_N_REGIONS)
                )
                geographic_distribution = {str(k): float(v) for k, v in top_regions.items()}

            return DemandResult(
                entity_name=entity_name,
                search_volume=search_volume,
                trend_velocity=trend_velocity,
                related_queries=related_queries,
                geographic_distribution=geographic_distribution,
            )

        except Exception as e:
            return DemandResult(
                entity_name=entity_name,
                search_volume=None,
                trend_velocity=None,
                error=str(e),
            )
