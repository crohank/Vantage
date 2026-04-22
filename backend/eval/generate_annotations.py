"""
Annotation Generator

Uses Gemini to generate synthetic financial queries for each intent category.
Outputs to annotations_draft.json for human review.

Usage:
    python eval/generate_annotations.py
    python eval/generate_annotations.py --count 10   # 10 per category
"""

import os
import sys
import json
import argparse
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.llm_service import get_gemini_service


EVAL_DIR = os.path.dirname(__file__)
TAXONOMY_PATH = os.path.join(EVAL_DIR, "intent_taxonomy.yaml")
OUTPUT_PATH = os.path.join(EVAL_DIR, "annotations_draft.json")


def load_taxonomy():
    with open(TAXONOMY_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def generate_queries_for_category(category: dict, count: int = 20) -> list:
    """Generate synthetic queries for a single intent category."""
    gemini = get_gemini_service()

    prompt = f"""Generate {count} realistic user queries for a financial analysis chatbot.

Category: {category['name']}
Description: {category['description']}
Example queries: {json.dumps(category['examples'])}

Requirements:
- Each query should be natural and varied (different phrasing, different stocks)
- Include a mix of simple (single stock, clear intent) and multi-hop (multiple entities or implied parameters) queries
- Use real US stock tickers/company names
- Vary the tone: casual, professional, terse, verbose

Return ONLY a JSON array of objects:
[
  {{
    "query": "the user query text",
    "expected_ticker": "AAPL or null",
    "complexity": "simple or multi-hop",
    "notes": "any edge case notes"
  }}
]"""

    try:
        results = gemini.invoke_json(prompt, temperature=0.8)
        if isinstance(results, list):
            return results
        return []
    except Exception as e:
        print(f"  Error generating for {category['name']}: {e}")
        return []


def main():
    parser = argparse.ArgumentParser(description="Generate annotation candidates")
    parser.add_argument("--count", type=int, default=20, help="Queries per category")
    args = parser.parse_args()

    taxonomy = load_taxonomy()
    categories = taxonomy["taxonomy"]["categories"]

    all_annotations = []
    next_id = 100  # Start IDs at 100 to avoid collision with manual annotations

    for category in categories:
        print(f"Generating {args.count} queries for '{category['name']}'...")
        queries = generate_queries_for_category(category, count=args.count)

        for q in queries:
            all_annotations.append({
                "id": next_id,
                "query": q.get("query", ""),
                "intent": category["name"],
                "expected_ticker": q.get("expected_ticker"),
                "complexity": q.get("complexity", "simple"),
                "source": "llm_generated",
                "human_verified": False,
                "notes": q.get("notes", ""),
            })
            next_id += 1

        print(f"  Generated {len(queries)} queries")

    # Write draft
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(all_annotations, f, indent=2, ensure_ascii=False)

    print(f"\nTotal annotations generated: {len(all_annotations)}")
    print(f"Saved to: {OUTPUT_PATH}")
    print("Review and merge verified annotations into annotations.json")


if __name__ == "__main__":
    main()
