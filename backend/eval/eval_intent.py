"""
Intent Classification Evaluator

Evaluates the query resolver's ability to correctly resolve tickers
and classify intent against the annotated dataset.

Usage:
    python eval/eval_intent.py
    python eval/eval_intent.py --only-verified    # Only human-verified annotations
"""

import os
import sys
import json
import csv
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.query_resolver import resolve_query, is_likely_ticker


EVAL_DIR = os.path.dirname(__file__)
ANNOTATIONS_PATH = os.path.join(EVAL_DIR, "annotations.json")
RESULTS_DIR = os.path.join(EVAL_DIR, "results")


def load_annotations(only_verified: bool = False):
    with open(ANNOTATIONS_PATH, "r", encoding="utf-8") as f:
        annotations = json.load(f)
    if only_verified:
        annotations = [a for a in annotations if a.get("human_verified", False)]
    return annotations


def evaluate_ticker_resolution(annotation: dict) -> dict:
    """Run query resolver and compare against expected ticker."""
    query = annotation["query"]
    expected_ticker = annotation.get("expected_ticker")

    # Skip direct ticker inputs (trivial)
    if is_likely_ticker(query.strip().upper()):
        return {
            "id": annotation["id"],
            "query": query,
            "intent": annotation["intent"],
            "expected_ticker": expected_ticker,
            "resolved_ticker": query.strip().upper(),
            "ticker_correct": query.strip().upper() == expected_ticker,
            "confidence": 1.0,
            "skipped": True,
            "error": None,
        }

    try:
        result = resolve_query(query)
        resolved_ticker = result.get("ticker")
        confidence = result.get("confidence", 0)

        # Ticker match: case-insensitive comparison
        if expected_ticker is None:
            ticker_correct = resolved_ticker is None
        elif resolved_ticker is None:
            ticker_correct = False
        else:
            ticker_correct = resolved_ticker.upper() == expected_ticker.upper()

        return {
            "id": annotation["id"],
            "query": query,
            "intent": annotation["intent"],
            "expected_ticker": expected_ticker,
            "resolved_ticker": resolved_ticker,
            "ticker_correct": ticker_correct,
            "confidence": confidence,
            "skipped": False,
            "error": result.get("error"),
        }

    except Exception as e:
        return {
            "id": annotation["id"],
            "query": query,
            "intent": annotation["intent"],
            "expected_ticker": expected_ticker,
            "resolved_ticker": None,
            "ticker_correct": False,
            "confidence": 0,
            "skipped": False,
            "error": str(e),
        }


def run_eval(only_verified: bool = False):
    annotations = load_annotations(only_verified)
    print(f"Evaluating {len(annotations)} annotations...")
    print()

    os.makedirs(RESULTS_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(RESULTS_DIR, f"intent_eval_{timestamp}.csv")

    results = []
    correct = 0
    total_non_skipped = 0

    for i, annotation in enumerate(annotations):
        print(f"[{i+1}/{len(annotations)}] \"{annotation['query'][:50]}...\"")
        result = evaluate_ticker_resolution(annotation)
        results.append(result)

        if not result["skipped"]:
            total_non_skipped += 1
            if result["ticker_correct"]:
                correct += 1
                print(f"  OK: {result['resolved_ticker']} (conf: {result['confidence']:.2f})")
            else:
                print(f"  MISS: expected={result['expected_ticker']}, got={result['resolved_ticker']} (conf: {result['confidence']:.2f})")
        else:
            print(f"  SKIP: direct ticker input")

    # Write CSV
    if results:
        fieldnames = list(results[0].keys())
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)
        print(f"\nResults saved to: {csv_path}")

    # Summary
    accuracy = (correct / total_non_skipped * 100) if total_non_skipped > 0 else 0
    skipped = len(results) - total_non_skipped

    # Per-intent breakdown
    intent_stats = {}
    for r in results:
        if r["skipped"]:
            continue
        intent = r["intent"]
        if intent not in intent_stats:
            intent_stats[intent] = {"correct": 0, "total": 0}
        intent_stats[intent]["total"] += 1
        if r["ticker_correct"]:
            intent_stats[intent]["correct"] += 1

    print(f"\n{'='*50}")
    print(f"INTENT EVALUATION SUMMARY")
    print(f"{'='*50}")
    print(f"Total annotations: {len(results)}")
    print(f"Skipped (direct tickers): {skipped}")
    print(f"Evaluated: {total_non_skipped}")
    print(f"Correct: {correct}")
    print(f"Ticker Resolution Accuracy: {accuracy:.1f}%")
    print(f"\nPer-Intent Breakdown:")
    for intent, stats in sorted(intent_stats.items()):
        intent_acc = (stats['correct'] / stats['total'] * 100) if stats['total'] > 0 else 0
        print(f"  {intent:<20} {stats['correct']}/{stats['total']} ({intent_acc:.0f}%)")
    print(f"{'='*50}")


def main():
    parser = argparse.ArgumentParser(description="Evaluate intent classification")
    parser.add_argument("--only-verified", action="store_true",
                        help="Only evaluate human-verified annotations")
    args = parser.parse_args()

    run_eval(only_verified=args.only_verified)


if __name__ == "__main__":
    main()
