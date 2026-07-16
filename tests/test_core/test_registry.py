"""Tests for provenance/core/registry.py (PLAN.md section 14 Test File Structure)."""
from __future__ import annotations

import pytest

from provenance.core.registry import _Registry
from provenance.probes.base import BaseProbe


class _FakeProbe(BaseProbe):
    provider_name = "fake"

    async def probe(self, query, query_variant, entity_name, context, competitors=None):
        raise NotImplementedError

    def _build_prompt(self, query, entity_name, context):
        return query

    def _extract_entities(self, raw_response, entity_name, competitors):
        return []


class _NotAProbe:
    pass


def test_registry_register_get_list_all():
    registry = _Registry(BaseProbe)
    registry.register("fake", _FakeProbe)

    assert registry.get("fake") is _FakeProbe
    assert registry.list() == ["fake"]
    assert registry.all() == {"fake": _FakeProbe}


def test_registry_get_unknown_raises_key_error():
    registry = _Registry(BaseProbe)
    with pytest.raises(KeyError):
        registry.get("missing")


def test_registry_register_rejects_wrong_base_class():
    registry = _Registry(BaseProbe)
    with pytest.raises(TypeError):
        registry.register("bad", _NotAProbe)
