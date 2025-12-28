"""
Scenario Analysis Agent

Responsibility: Generate Bull/Base/Bear scenarios with probabilities.
"""

import time
from typing import Dict, Any
from schemas.state import ResearchState
import json


def scenario_agent(state: ResearchState) -> ResearchState:
    """
    Scenario Analysis Agent - Generates Bull/Base/Bear scenarios.
    
    Args:
        state: Current research state
    
    Returns:
        Updated state with scenarios populated
    """
    ticker = state.get("ticker", "")
    horizon = state.get("horizon", "medium")
    market_data = state.get("market_data", {})
    macro_data = state.get("macro_data", {})
    risk_analysis = state.get("risk_analysis", {})
    
    agent_start = time.time()
    print(f"\n[Scenario Agent] Calling Gemini API...")
    
    try:
        from services.llm_service import get_gemini_service
        
        gemini = get_gemini_service()
        llm_start = time.time()
        
        # Explicit schema with probability constraints
        prompt = f"""Generate scenarios for {ticker} ({horizon}-term horizon):

Market Context:
- Price Trend: {market_data.get('price_trend', 'Unknown')}
- P/E Ratio: {market_data.get('valuation', {}).get('pe_ratio', 'Unknown')}
- RSI: {market_data.get('technical_indicators', {}).get('rsi', 'Unknown')}

Macro Context:
- Interest Rate Trend: {macro_data.get('interest_rate_trend', 'Unknown')}
- Inflation Trend: {macro_data.get('inflation_trend', 'Unknown')}
- Market Trend: {macro_data.get('market_trend', 'Unknown')}

Risk Context:
- Volatility: {risk_analysis.get('volatility', 'Unknown')}
- Beta: {risk_analysis.get('beta', 'Unknown')}
- Key Risks: {', '.join(risk_analysis.get('key_risks', []))}

Return JSON schema:
{{
  "bull": {{"return": float, "prob": float}},
  "base": {{"return": float, "prob": float}},
  "bear": {{"return": float, "prob": float}}
}}

Constraints:
- prob values must sum to 1.0
- return values as decimals (e.g., 0.25 for 25%)"""

        scenarios = gemini.invoke_json(prompt, temperature=0.7)
        llm_time = time.time() - llm_start
        print(f"[OK] Scenario generation complete in {llm_time:.1f}s")
        
        # Validate and normalize probabilities
        total_prob = scenarios.get("bull", {}).get("prob", 0) + \
                    scenarios.get("base", {}).get("prob", 0) + \
                    scenarios.get("bear", {}).get("prob", 0)
        
        if total_prob > 0:
            # Normalize probabilities
            for scenario in ["bull", "base", "bear"]:
                if scenario in scenarios:
                    scenarios[scenario]["prob"] = scenarios[scenario]["prob"] / total_prob
        else:
            # Default probabilities if invalid
            scenarios = {
                "bull": {"return": 0.20, "prob": 0.30},
                "base": {"return": 0.05, "prob": 0.50},
                "bear": {"return": -0.15, "prob": 0.20}
            }
        
        state["scenarios"] = scenarios
        agent_time = time.time() - agent_start
        print(f"[Scenario Agent] Complete in {agent_time:.1f}s (LLM: {llm_time:.1f}s).")
        
        # Store timing
        state["_agent_timing"] = state.get("_agent_timing", {})
        state["_agent_timing"]["scenario_analysis"] = agent_time
        state["_agent_timing"]["scenario_analysis_llm"] = llm_time
        
    except Exception as e:
        agent_time = time.time() - agent_start
        print(f"Error generating scenarios after {agent_time:.1f}s: {e}")
        # Default scenarios on error
        state["scenarios"] = {
            "bull": {"return": 0.20, "prob": 0.30},
            "base": {"return": 0.05, "prob": 0.50},
            "bear": {"return": -0.15, "prob": 0.20}
        }
    
    return state
