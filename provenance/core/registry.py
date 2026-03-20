from typing import Dict, List, Type


class _Registry:
    """
    Generic class registry. Holds class references keyed by string names.
    Instances are created by the caller — the registry holds class refs, not instances.
    """

    def __init__(self, base_class: type):
        self._base_class = base_class
        self._registry: Dict[str, type] = {}

    def register(self, name: str, cls: type) -> None:
        if not issubclass(cls, self._base_class):
            raise TypeError(
                f"{cls.__name__} must be a subclass of {self._base_class.__name__}"
            )
        self._registry[name] = cls

    def get(self, name: str) -> type:
        if name not in self._registry:
            raise KeyError(
                f"No registered implementation for '{name}'. "
                f"Available: {list(self._registry.keys())}"
            )
        return self._registry[name]

    def list(self) -> List[str]:
        return list(self._registry.keys())

    def all(self) -> Dict[str, type]:
        return dict(self._registry)


# Deferred imports to avoid circular dependency at module load time.
# Registries are populated during app startup in main.py.
def _make_probe_registry() -> _Registry:
    from provenance.probes.base import BaseProbe
    return _Registry(BaseProbe)


def _make_collector_registry() -> _Registry:
    from provenance.collectors.base import BaseCollector
    return _Registry(BaseCollector)


ProbeRegistry: _Registry = _make_probe_registry()
CollectorRegistry: _Registry = _make_collector_registry()
