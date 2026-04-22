"""Mongo-backed telemetry service."""

from datetime import datetime
from typing import Any, Dict, Optional

from services.mongo_client import get_db


# Cost per 1M tokens (USD) — update as pricing changes
MODEL_PRICING = {
    # Gemini Flash models (free tier for now, but track anyway)
    "gemini-2.5-flash": {"input": 0.15, "output": 0.60},
    "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
    "gemini-2.5-pro": {"input": 1.25, "output": 5.00},
    "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
    "gemini-pro": {"input": 0.50, "output": 1.50},
    # HuggingFace (inference API — estimate)
    "mistralai/Mistral-7B-Instruct-v0.2": {"input": 0.10, "output": 0.10},
}

# Default pricing for unknown models
DEFAULT_PRICING = {"input": 0.50, "output": 1.50}


class TelemetryDB:
    """Mongo-backed telemetry storage for LLM call tracking."""

    def log_call(
        self,
        agent_name: str,
        model: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        latency_ms: float = 0,
        analysis_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """Log a single LLM call."""
        total_tokens = prompt_tokens + completion_tokens
        cost = self._estimate_cost(model, prompt_tokens, completion_tokens)

        get_db()["telemetry"].insert_one(
            {
                "timestamp": datetime.utcnow(),
                "analysis_id": analysis_id,
                "agent_name": agent_name,
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "latency_ms": latency_ms,
                "cost_usd": cost,
                "error": error,
            }
        )

        print(
            f"[Telemetry] {agent_name} | {model} | "
            f"{prompt_tokens}+{completion_tokens}={total_tokens} tokens | "
            f"{latency_ms:.0f}ms | ${cost:.6f}"
        )

    def get_analysis_summary(self, analysis_id: str) -> Dict[str, Any]:
        """Get aggregated telemetry for an entire analysis run."""
        rows = list(get_db()["telemetry"].find({"analysis_id": analysis_id}).sort("timestamp", 1))
        if not rows:
            return {"analysis_id": analysis_id, "calls": [], "totals": {}}

        calls = []
        total_prompt = 0
        total_completion = 0
        total_cost = 0.0
        total_latency = 0.0

        for row in rows:
            call = dict(row)
            call["_id"] = str(call.get("_id", ""))
            calls.append(call)
            total_prompt += call["prompt_tokens"]
            total_completion += call["completion_tokens"]
            total_cost += call["cost_usd"]
            total_latency += call["latency_ms"]

        return {
            "analysis_id": analysis_id,
            "calls": calls,
            "totals": {
                "prompt_tokens": total_prompt,
                "completion_tokens": total_completion,
                "total_tokens": total_prompt + total_completion,
                "total_cost_usd": round(total_cost, 6),
                "total_latency_ms": round(total_latency, 1),
                "num_calls": len(calls),
            },
        }

    @staticmethod
    def _estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """Estimate cost in USD based on model pricing."""
        pricing = MODEL_PRICING.get(model, DEFAULT_PRICING)
        input_cost = (prompt_tokens / 1_000_000) * pricing["input"]
        output_cost = (completion_tokens / 1_000_000) * pricing["output"]
        return input_cost + output_cost

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Rough token estimate: ~4 chars per token for English text."""
        return max(1, len(text) // 4)


# Global singleton
_telemetry_db: Optional[TelemetryDB] = None


def get_telemetry_db() -> TelemetryDB:
    """Get or create the global TelemetryDB instance."""
    global _telemetry_db
    if _telemetry_db is None:
        _telemetry_db = TelemetryDB()
    return _telemetry_db
