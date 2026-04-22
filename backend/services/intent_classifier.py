"""
Intent Classifier

Classifies user queries into the financial intent taxonomy.
Can be integrated with the query resolver for intent-aware routing.
"""

import os
import json
import yaml
from typing import Dict, Any
from services.llm_service import get_gemini_service


TAXONOMY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "eval", "intent_taxonomy.yaml"
)


def _load_taxonomy() -> Dict[str, Any]:
    """Load the intent taxonomy."""
    with open(TAXONOMY_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def classify_intent(query: str) -> Dict[str, Any]:
    """
    Classify a user query into the financial intent taxonomy.

    Args:
        query: User's natural language query

    Returns:
        Dict with keys:
        - intent: Category name (e.g., "stock_analysis")
        - confidence: 0.0-1.0
        - reasoning: Brief explanation
    """
    taxonomy = _load_taxonomy()
    categories = taxonomy["taxonomy"]["categories"]

    # Build category descriptions for the prompt
    category_desc = "\n".join(
        f"- {c['name']}: {c['description']}"
        for c in categories
    )

    prompt = f"""Classify this financial query into one of the following intent categories:

{category_desc}

Query: "{query}"

Return ONLY valid JSON:
{{"intent": "category_name", "confidence": 0.0-1.0, "reasoning": "brief explanation"}}"""

    try:
        gemini = get_gemini_service()
        result = gemini.invoke_json(prompt, temperature=0.1)

        intent = result.get("intent", "stock_analysis")
        valid_intents = [c["name"] for c in categories]
        if intent not in valid_intents:
            intent = "stock_analysis"  # Default fallback

        return {
            "intent": intent,
            "confidence": result.get("confidence", 0.5),
            "reasoning": result.get("reasoning", ""),
        }

    except Exception as e:
        print(f"[Intent Classifier] Error: {e}")
        return {
            "intent": "stock_analysis",
            "confidence": 0.0,
            "reasoning": f"Classification failed: {e}",
        }
