"""
Evaluation Harness

Runs prompt versions against the golden dataset and scores outputs using LLM-as-judge.

Usage:
    python eval/run_eval.py                          # Run all with latest prompt versions
    python eval/run_eval.py --prompt-version 1       # Run with specific prompt version
    python eval/run_eval.py --agent risk_analysis    # Run only risk_analysis examples
"""

import os
import sys
import json
import csv
import time
import argparse
from datetime import datetime

# Add parent dir to path so we can import project modules
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from services.llm_service import get_gemini_service
from services.prompt_manager import render_prompt, load_prompt


EVAL_DIR = os.path.dirname(__file__)
GOLDEN_SET_PATH = os.path.join(EVAL_DIR, "golden_set.json")
JUDGE_PROMPT_PATH = os.path.join(EVAL_DIR, "judge_prompt.yaml")
RESULTS_DIR = os.path.join(EVAL_DIR, "results")


def load_golden_set(agent_filter: str = None):
    """Load golden dataset, optionally filtered by agent type."""
    with open(GOLDEN_SET_PATH, "r", encoding="utf-8") as f:
        examples = json.load(f)
    if agent_filter:
        examples = [e for e in examples if e["agent"] == agent_filter]
    return examples


def load_judge_prompt():
    """Load the judge prompt template."""
    import yaml
    with open(JUDGE_PROMPT_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run_agent_prompt(example: dict, prompt_version: int = None):
    """Run the appropriate agent prompt for an example and return output + latency."""
    agent = example["agent"]
    ctx = example["input_context"]

    start = time.perf_counter()

    gemini = get_gemini_service()

    # Map agent type to prompt name and build variables
    if agent == "risk_analysis":
        prompt = render_prompt("risk_analysis", ctx, version=prompt_version)
        prompt_data = load_prompt("risk_analysis", version=prompt_version)
        temp = prompt_data.get("temperature", 0.5)
        output = gemini.invoke(prompt, temperature=temp)
    elif agent == "scenario_generation":
        prompt = render_prompt("scenario_generation", ctx, version=prompt_version)
        prompt_data = load_prompt("scenario_generation", version=prompt_version)
        temp = prompt_data.get("temperature", 0.7)
        output = gemini.invoke(prompt, temperature=temp)
    else:
        output = f"Unknown agent type: {agent}"

    latency_ms = (time.perf_counter() - start) * 1000
    return output, latency_ms


def judge_output(example: dict, actual_output: str):
    """Use LLM-as-judge to score the output."""
    judge_data = load_judge_prompt()
    template = judge_data["template"]

    # Build judge prompt
    class SafeDict(dict):
        def __missing__(self, key):
            return f"{{{key}}}"

    prompt = template.format_map(SafeDict(
        agent_type=example["agent"],
        ticker=example["ticker"],
        input_context=json.dumps(example["input_context"], indent=2),
        expected_keywords=", ".join(example.get("expected_output_contains", [])),
        actual_output=actual_output[:2000],  # Truncate to avoid token limits
    ))

    gemini = get_gemini_service()
    try:
        result = gemini.invoke_json(prompt, temperature=0.2)
        return {
            "relevance": result.get("relevance", 0),
            "accuracy": result.get("accuracy", 0),
            "reasoning": result.get("reasoning", ""),
        }
    except Exception as e:
        print(f"  Judge error: {e}")
        return {"relevance": 0, "accuracy": 0, "reasoning": f"Judge error: {e}"}


def run_eval(prompt_version: int = None, agent_filter: str = None):
    """Run the full evaluation loop."""
    examples = load_golden_set(agent_filter)
    print(f"Running evaluation on {len(examples)} examples...")
    if prompt_version:
        print(f"Using prompt version: v{prompt_version}")
    print()

    os.makedirs(RESULTS_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(RESULTS_DIR, f"eval_{timestamp}.csv")

    results = []

    for i, example in enumerate(examples):
        print(f"[{i+1}/{len(examples)}] {example['ticker']} - {example['agent']} (id={example['id']})")

        # Run the agent prompt
        try:
            output, latency_ms = run_agent_prompt(example, prompt_version)
            print(f"  Output: {output[:100]}...")
            print(f"  Latency: {latency_ms:.0f}ms")
        except Exception as e:
            print(f"  Error running prompt: {e}")
            output = f"Error: {e}"
            latency_ms = 0

        # Judge the output
        print(f"  Judging...")
        scores = judge_output(example, output)
        print(f"  Relevance: {scores['relevance']}/5, Accuracy: {scores['accuracy']}/5")
        print(f"  Reasoning: {scores['reasoning'][:100]}")
        print()

        results.append({
            "id": example["id"],
            "ticker": example["ticker"],
            "agent": example["agent"],
            "prompt_version": prompt_version or "latest",
            "relevance_score": scores["relevance"],
            "accuracy_score": scores["accuracy"],
            "latency_ms": round(latency_ms, 1),
            "model": "gemini-2.5-flash",
            "timestamp": datetime.now().isoformat(),
            "judge_reasoning": scores["reasoning"],
        })

    # Write CSV
    if results:
        fieldnames = list(results[0].keys())
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)
        print(f"Results saved to: {csv_path}")

    # Print summary
    if results:
        avg_relevance = sum(r["relevance_score"] for r in results) / len(results)
        avg_accuracy = sum(r["accuracy_score"] for r in results) / len(results)
        avg_latency = sum(r["latency_ms"] for r in results) / len(results)
        print(f"\n{'='*50}")
        print(f"EVALUATION SUMMARY")
        print(f"{'='*50}")
        print(f"Examples: {len(results)}")
        print(f"Avg Relevance: {avg_relevance:.2f}/5")
        print(f"Avg Accuracy:  {avg_accuracy:.2f}/5")
        print(f"Avg Latency:   {avg_latency:.0f}ms")
        print(f"{'='*50}")

    return results


def main():
    parser = argparse.ArgumentParser(description="Run prompt evaluation harness")
    parser.add_argument("--prompt-version", type=int, default=None,
                        help="Specific prompt version to test")
    parser.add_argument("--agent", type=str, default=None,
                        help="Filter by agent type (risk_analysis, scenario_generation)")
    args = parser.parse_args()

    run_eval(prompt_version=args.prompt_version, agent_filter=args.agent)


if __name__ == "__main__":
    main()
