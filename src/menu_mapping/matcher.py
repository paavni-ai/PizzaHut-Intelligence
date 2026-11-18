"""Conservative, explainable menu match suggestions."""
import re
from difflib import SequenceMatcher
from typing import Any, Mapping

_SIZE_WORDS = {"small", "medium", "large", "personal", "xl", "xlarge", "extra", "family"}
_STOP_WORDS = {"pizza", "the", "with", "and", "of"}


def _tokens(value: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", (value or "").casefold())
    return {word for word in words if word not in _SIZE_WORDS and word not in _STOP_WORDS}


def _jaccard(left: str, right: str) -> float:
    a, b = _tokens(left), _tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def score_menu_candidate(source: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, Any]:
    """Score a candidate while refusing size/category mismatches.

    Scores are ranking hints, not probabilities. Even high scores stay pending
    until a person explicitly approves the match.
    """
    if source.get("normalized_size") != candidate.get("normalized_size"):
        return {"suggested": False, "score": 0.0, "reason": "Size differs; never auto-matched."}
    if source.get("category_id") != candidate.get("category_id"):
        return {"suggested": False, "score": 0.0, "reason": "Category differs; review manually."}

    source_name = source.get("normalized_name") or source.get("item_name") or ""
    candidate_name = candidate.get("normalized_name") or candidate.get("name") or ""
    token_score = _jaccard(source_name, candidate_name)
    text_score = SequenceMatcher(None, " ".join(sorted(_tokens(source_name))), " ".join(sorted(_tokens(candidate_name)))).ratio()
    name_score = 0.65 * token_score + 0.35 * text_score
    reasons = [f"same size and category; name score {name_score:.2f}"]

    source_ingredients = source.get("ingredients") or ""
    candidate_ingredients = candidate.get("ingredients") or ""
    score = name_score
    if source_ingredients and candidate_ingredients:
        ingredient_score = _jaccard(source_ingredients, candidate_ingredients)
        score = 0.65 * name_score + 0.35 * ingredient_score
        reasons.append(f"ingredient overlap {ingredient_score:.2f}")
        if ingredient_score < 0.35:
            reasons.append("ingredients differ; manual review required")

    source_crust = (source.get("crust_type") or "").strip().casefold()
    candidate_crust = (candidate.get("crust_type") or "").strip().casefold()
    if source_crust and candidate_crust and source_crust != candidate_crust:
        score *= 0.8
        reasons.append("crust differs; manual review required")

    return {
        "suggested": score >= 0.35,
        "score": round(max(0.0, min(1.0, score)), 4),
        "reason": "; ".join(reasons),
    }
