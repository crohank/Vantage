"""
Investment Memo Writer Agent

Responsibility: Generate professional investment memo in Markdown format.
"""

import time
from typing import Dict, Any
from schemas.state import ResearchState
import os


def calculate_confidence_score(state: ResearchState) -> float:
    """
    Calculate confidence score based on data completeness and quality.
    
    Args:
        state: Current research state
    
    Returns:
        Confidence score between 0 and 1
    """
    # Data completeness (0.3 weight)
    completeness = 1.0
    if not state.get("market_data") or state.get("market_data", {}).get("error"):
        completeness -= 0.3
    if not state.get("macro_data") or state.get("macro_data", {}).get("error"):
        completeness -= 0.2
    if not state.get("risk_analysis") or state.get("risk_analysis", {}).get("error"):
        completeness -= 0.2
    if not state.get("scenarios"):
        completeness -= 0.3
    
    completeness = max(0.0, completeness)
    
    # Volatility penalty (0.3 weight)
    volatility = state.get("risk_analysis", {}).get("volatility", 0.3)
    volatility_score = max(0.0, 1.0 - volatility)  # Lower volatility = higher score
    
    # Agent agreement (0.4 weight) - simplified for now
    agreement = 0.7  # Placeholder - can be enhanced with actual agreement metrics
    
    # Calculate final confidence
    confidence = (
        completeness * 0.3 +
        agreement * 0.4 +
        volatility_score * 0.3
    )
    
    return round(max(0.0, min(1.0, confidence)), 2)


def determine_recommendation(state: ResearchState) -> str:
    """
    Determine Buy/Hold/Sell recommendation based on scenarios and data.
    
    Args:
        state: Current research state
    
    Returns:
        Recommendation: "Buy", "Hold", or "Sell"
    """
    scenarios = state.get("scenarios", {})
    
    if not scenarios:
        return "Hold"
    
    # Calculate expected return
    expected_return = (
        scenarios.get("bull", {}).get("return", 0) * scenarios.get("bull", {}).get("prob", 0) +
        scenarios.get("base", {}).get("return", 0) * scenarios.get("base", {}).get("prob", 0) +
        scenarios.get("bear", {}).get("return", 0) * scenarios.get("bear", {}).get("prob", 0)
    )
    
    # Get risk metrics
    risk_analysis = state.get("risk_analysis", {})
    volatility = risk_analysis.get("volatility", 0.3)
    
    # Determine recommendation
    if expected_return > 0.10 and volatility < 0.4:
        return "Buy"
    elif expected_return < -0.05 or volatility > 0.5:
        return "Sell"
    else:
        return "Hold"


def memo_writer_agent(state: ResearchState) -> ResearchState:
    """
    Investment Memo Writer Agent - Generates professional investment memo.
    
    Args:
        state: Current research state
    
    Returns:
        Updated state with memo and recommendation populated
    """
    ticker = state.get("ticker", "")
    horizon = state.get("horizon", "medium")
    risk_profile = state.get("risk_profile", "moderate")
    
    agent_start = time.time()
    print(f"\n[Memo Writer Agent] Generating investment memo...")
    
    # Calculate confidence and recommendation
    confidence = calculate_confidence_score(state)
    recommendation = determine_recommendation(state)
    
    state["confidence_score"] = confidence
    state["recommendation"] = recommendation
    
    print(f"[Memo Writer Agent] Recommendation: {recommendation}, Confidence: {confidence}")
    
    # Generate memo
    try:
        from services.llm_service import get_gemini_service
        
        gemini = get_gemini_service()
        print("[Memo Writer Agent] Calling Gemini API...")
        
        llm_start = time.time()
        market_data = state.get("market_data", {})
        macro_data = state.get("macro_data", {})
        risk_analysis = state.get("risk_analysis", {})
        scenarios = state.get("scenarios", {})
        
        # Structured markdown format prompt
        prompt = f"""Write investment memo for {ticker} ({horizon} term, {risk_profile} risk):

Key Data:
- Recommendation: {recommendation} (Confidence: {confidence:.0%})
- Price Trend: {market_data.get('price_trend', 'N/A')}, P/E: {market_data.get('valuation', {}).get('pe_ratio', 'N/A')}
- Macro: {macro_data.get('interest_rate_trend', 'N/A')} rates, {macro_data.get('market_trend', 'N/A')} market
- Risk: Vol {risk_analysis.get('volatility', 'N/A')}, Beta {risk_analysis.get('beta', 'N/A')}
- Scenarios: Bull {scenarios.get('bull', {}).get('return', 0)*100:+.0f}% ({scenarios.get('bull', {}).get('prob', 0)*100:.0f}%), Base {scenarios.get('base', {}).get('return', 0)*100:+.0f}% ({scenarios.get('base', {}).get('prob', 0)*100:.0f}%), Bear {scenarios.get('bear', {}).get('return', 0)*100:+.0f}% ({scenarios.get('bear', {}).get('prob', 0)*100:.0f}%)

Format: Markdown with sections:
1. Executive Summary
2. Thesis
3. Supporting Data
4. Risks
5. Scenarios
6. Recommendation
7. Disclaimer

Tone: Professional, no hype language"""

        memo = gemini.invoke(prompt, temperature=0.3)
        llm_time = time.time() - llm_start
        print(f"[OK] Memo generation complete in {llm_time:.1f}s")
        
        state["memo"] = memo
        
        # Save memo to file
        outputs_dir = "outputs"
        os.makedirs(outputs_dir, exist_ok=True)
        memo_file = os.path.join(outputs_dir, f"{ticker}_memo.md")
        
        with open(memo_file, "w", encoding="utf-8") as f:
            f.write(memo)
        
        agent_time = time.time() - agent_start
        print(f"Memo saved to {memo_file} (took {agent_time:.1f}s, LLM: {llm_time:.1f}s)")
        
        # Store timing
        state["_agent_timing"] = state.get("_agent_timing", {})
        state["_agent_timing"]["memo_writer"] = agent_time
        state["_agent_timing"]["memo_writer_llm"] = llm_time
        
    except Exception as e:
        agent_time = time.time() - agent_start
        print(f"Error generating memo after {agent_time:.1f}s: {e}")
        state["memo"] = f"Error generating memo: {str(e)}"
    
    return state
