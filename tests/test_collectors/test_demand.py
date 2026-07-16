"""Tests for provenance/collectors/demand.py (PLAN.md section 14, Collectors 5-6)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd

from provenance.collectors.demand import DemandCollector


def _fake_pytrends(iot_df=None, related=None, region_df=None, build_payload_error=None):
    fake = MagicMock()
    if build_payload_error is not None:
        fake.build_payload.side_effect = build_payload_error
    fake.interest_over_time.return_value = iot_df
    fake.related_queries.return_value = related
    fake.interest_by_region.return_value = region_df
    return fake


def test_demand_collector_happy_path(test_settings):
    collector = DemandCollector(test_settings)
    values = [float(50 + (i % 10)) for i in range(90)]
    iot_df = pd.DataFrame({"Acme": values})
    rising_df = pd.DataFrame({"query": ["acme alternative", "acme pricing"]})
    region_df = pd.DataFrame(
        {"Acme": {"US": 90.0, "IN": 80.0, "GB": 70.0, "CA": 60.0, "DE": 50.0, "FR": 40.0}}
    )
    collector._pytrends = _fake_pytrends(
        iot_df=iot_df, related={"Acme": {"rising": rising_df}}, region_df=region_df
    )

    result = collector.collect("Acme", "graph database")

    assert result.error is None
    assert result.entity_name == "Acme"
    assert result.search_volume == round(sum(values) / len(values), 2)
    recent_30 = values[-30:]
    prior_30 = values[-60:-30]
    expected_velocity = round(sum(recent_30) / 30 - sum(prior_30) / 30, 2)
    assert result.trend_velocity == expected_velocity
    assert result.related_queries == ["acme alternative", "acme pricing"]
    assert len(result.geographic_distribution) == 5
    assert result.geographic_distribution["US"] == 90.0
    assert "FR" not in result.geographic_distribution


def test_demand_collector_degrades_on_exception(test_settings):
    collector = DemandCollector(test_settings)
    collector._pytrends = _fake_pytrends(build_payload_error=RuntimeError("rate limited"))

    result = collector.collect("Acme", "graph database")

    assert result.error == "rate limited"
    assert result.search_volume is None
    assert result.trend_velocity is None
    assert result.related_queries == []
    assert result.geographic_distribution == {}


def test_demand_collector_degrades_on_empty_interest_over_time(test_settings):
    collector = DemandCollector(test_settings)
    collector._pytrends = _fake_pytrends(iot_df=pd.DataFrame())

    result = collector.collect("Acme", "graph database")

    assert result.error == "pytrends returned no interest_over_time data"
    assert result.search_volume is None
