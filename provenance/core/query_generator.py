"""
Query matrix generator — expands entity query seeds into a full probe matrix.

Output: seeds × variants × perturbations (all template-based, no LLM calls).
Variance comes from LLM responses, not query construction.
"""
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class GeneratedQuery:
    text: str
    variant: str           # "direct" | "comparative" | "expert" | "contrarian"
    perturbation_index: int  # 0 = canonical, 1+ = surface rephrasing


# Surface rephrasings — same intent, different phrasing. Tests LLM sensitivity to framing.
_PERTURBATION_WRAPPERS = [
    "{query}",                          # 0: canonical
    "I'm evaluating options. {query}",  # 1: evaluation framing
    "Help me understand this: {query}", # 2: learning framing
]

_EXPERT_PREFIX = "From the perspective of an experienced practitioner: "
_CONTRARIAN_PREFIX = "What are the main criticisms or limitations? "
_COMPARATIVE_SUFFIX_GENERIC = " How does it compare to the main alternatives?"


class QueryGenerator:
    """
    Expands a list of query seeds into the full (variant × perturbation) probe matrix.

    Args:
        perturbations_per_variant: how many surface rephrasings to generate (max 3 in v1).
        variants: which variant types to include (defaults to all four).
    """

    ALL_VARIANTS = ["direct", "comparative", "expert", "contrarian"]

    def __init__(
        self,
        perturbations_per_variant: int = 3,
        variants: Optional[List[str]] = None,
    ):
        self.perturbations_per_variant = min(
            perturbations_per_variant, len(_PERTURBATION_WRAPPERS)
        )
        self.variants = variants or self.ALL_VARIANTS

    def generate(
        self,
        query_seeds: List[str],
        entity_name: str,
        competitors: Optional[List[str]] = None,
    ) -> List[GeneratedQuery]:
        """
        Returns the full probe matrix as a flat list of GeneratedQuery.
        Order: seed → variant → perturbation (innermost).
        """
        competitors = competitors or []
        results: List[GeneratedQuery] = []

        for seed in query_seeds:
            for variant in self.variants:
                base = self._apply_variant(seed, variant, entity_name, competitors)
                for i in range(self.perturbations_per_variant):
                    text = _PERTURBATION_WRAPPERS[i].format(query=base)
                    results.append(
                        GeneratedQuery(text=text, variant=variant, perturbation_index=i)
                    )

        return results

    def _apply_variant(
        self,
        seed: str,
        variant: str,
        entity_name: str,
        competitors: List[str],
    ) -> str:
        if variant == "direct":
            return seed

        if variant == "comparative":
            if competitors:
                names = ", ".join(competitors[:3])
                return f"{seed} How does {entity_name} compare to {names}?"
            return seed + _COMPARATIVE_SUFFIX_GENERIC

        if variant == "expert":
            return _EXPERT_PREFIX + seed

        if variant == "contrarian":
            return _CONTRARIAN_PREFIX + seed

        return seed  # unknown variant falls back to direct
